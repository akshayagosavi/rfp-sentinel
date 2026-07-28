"""
M9: extract_rfp_criteria() -- turns an uploaded RFP PDF into a clean list of
structured, checkable criteria.

mandatory/category/guidance-vs-criterion were originally decided by keyword
regex, a v1 shortcut to avoid adding a new, unproven LLM call under time
pressure. Switched to LLM classification (reusing backend.llm.ollama_client's
classify(), the same function every other classification in this project
goes through) once the remote qwen2.5:7b model was confirmed faster and
more reliable than the original local model -- see STATUS_REPORT.md's
"hardcoded shortcuts" audit for why this was revisited.
"""
import concurrent.futures
import functools
import re
import sys
from pathlib import Path

import pdfplumber

from backend.graph.extract_scoring_rule import infer_rule
from backend.llm.ollama_client import classify
from backend.logging_config import get_logger
from backend.models.rfp import Criterion, StructuredRFP
from backend.scoring.scoring import SCORED_CATEGORIES
from ingestion.chunker import chunk_document
from ingestion.extract_tables import PageTable, extract_tables_by_page
from ingestion.extract_text import PageText, extract_text_by_page
from ingestion.language_filter import filter_english

logger = get_logger(__name__)


# An exact-string match here (the original form) silently failed on real GeM
# documents that phrase this "null & void" instead of "null and void" --
# confirmed against two real RFPs (a desktop-computer bid and a server bid),
# both of which use "&". When this marker doesn't match, _extract_
# prohibited_practices() below returns [] with no error, and the entire
# buyer-facing disclaimer list (numbered clauses like "Asking for any Tender
# fee...", "Buyer added ATC Clauses which are in contravention...") silently
# leaks through as if it were real bidder criteria -- which then get sent to
# check_rfp_compliance() and produce nonsensical "norm conflict" flags on
# text that was never a bidder requirement in the first place. Tolerant of
# "and"/"&" and surrounding whitespace/line-break variation now; if another
# real document surfaces yet another phrasing, extend this pattern the same
# way rather than adding a second hardcoded exact string.
_PROHIBITED_PRACTICES_START = re.compile(r"shall\s+be\s+treated\s+as\s+null\s*(?:and|&)\s*void", re.IGNORECASE)
_PROHIBITED_PRACTICES_END = "Further, if any seller has any objection"

# GeM's own bid number, e.g. "GEM/2024/B/5735766" -- the real, official
# reference a bidder would actually search by on GeM itself, distinct from
# our own internal rfp_id (a random hex string, our database key, never
# shown to GeM). Confirmed as a unique, unambiguous match in the real
# NIELIT RFP -- appears exactly once in the whole document, right next to
# a "Bid Number" label, so a direct pattern match is reliable without
# needing a bounded label-window like the other two extractions below.
_GEM_BID_NUMBER_PATTERN = re.compile(r"GEM/\d{4}/[A-Z]/\d+")

_MIN_WORDS = 15  # skip tiny fragments that aren't real criteria

# Candidates (and, within a candidate, mandatory/category checks) are
# independent of each other, so they're safe to run concurrently. Bounded,
# not unlimited -- an empirical test (see STATUS_REPORT.md) showed the
# remote server has a real concurrency ceiling, and firing everything at
# once risks the same connection-reset failure classify()'s retry logic
# was built to recover from, not prevent outright.
_MAX_CONCURRENT_LLM_CALLS = 5


def _run_concurrent(pool: concurrent.futures.ThreadPoolExecutor, tasks: list, stage_label: str) -> list:
    """tasks is a list of zero-arg callables (e.g. functools.partial(fn, text)),
    all fanned out into the pool together -- callers combine heterogeneous
    task types (like mandatory + category checks) into one tasks list so
    they run fully concurrently with each other, not just within their own
    type. Logs a running 'N/total done' count as each one finishes, since
    answers can come back in any order once fanned out together."""
    total = len(tasks)
    futures = {pool.submit(task): idx for idx, task in enumerate(tasks)}
    results: list = [None] * total
    done = 0
    for future in concurrent.futures.as_completed(futures):
        idx = futures[future]
        results[idx] = future.result()
        done += 1
        logger.info("%s: %d/%d done", stage_label, done, total)
    return results


def _is_guidance_text(text: str) -> bool:
    """GeM bid PDFs end with buyer-facing instructional boilerplate (warnings
    about prohibited drafting practices, disclaimers) that reads like a
    numbered requirement but isn't something the bidder must satisfy. Used
    to be detected by a regex phrase-match confirmed against only one real
    document; an LLM judgment generalizes better across RFP templates."""
    result = classify(
        subject_text=text,
        references=[],
        verdict_options=["criterion", "guidance"],
        instruction=(
            "ROLE: You are reviewing one candidate clause pulled from a government RFP document.\n"
            "OBJECTIVE: Decide whether this clause is a real requirement the bidder must satisfy "
            "('criterion'), or text addressed to the buyer/drafter that imposes nothing on the "
            "bidder ('guidance').\n"
            "DECISION RULES:\n"
            "- Ask who this clause actually binds: does it impose an obligation, qualification, or "
            "condition that the BIDDER's submission or eligibility must satisfy, or does it "
            "instruct, remind, or caution whoever is PREPARING the RFP, with no obligation placed "
            "on the bidder?\n"
            "- If the clause states something the bidder must provide, meet, possess, or comply "
            "with, classify 'criterion' -- regardless of how it's phrased grammatically.\n"
            "- If the clause is a reminder, disclaimer, or drafting instruction aimed at the buyer, "
            "and does not itself impose anything a bidder must satisfy, classify 'guidance'.\n"
            "- Example: 'Bidders must submit audited financial statements for the last three "
            "years' is a criterion; 'This clause must not restrict competition and should comply "
            "with applicable procurement rules' is guidance."
        ),
    )
    return result.verdict == "guidance"


def _infer_mandatory(text: str) -> bool:
    result = classify(
        subject_text=text,
        references=[],
        verdict_options=["mandatory", "optional"],
        instruction=(
            "ROLE: You are reviewing one already-confirmed bidder-facing RFP criterion.\n"
            "OBJECTIVE: Decide whether compliance with it is mandatory or merely "
            "optional/preferential.\n"
            "DECISION RULES:\n"
            "- Ask what happens if a bidder does not meet this criterion: does the RFP's own "
            "wording treat that as disqualifying or invalidating the bid, or does it merely "
            "reduce a score, reflect a preference, or leave the matter to the buyer's discretion "
            "without disqualifying the bid?\n"
            "- If failing to meet it would disqualify or invalidate the bid, classify "
            "'mandatory'.\n"
            "- If it is framed as preferred, weighted, or discretionary, with no disqualifying "
            "consequence for not meeting it, classify 'optional'."
        ),
    )
    return result.verdict == "mandatory"


def _infer_category(text: str) -> str:
    """'other' is a genuine, honest answer, not an error case -- the three
    named categories don't cover every real RFP clause (e.g. quantity-split
    ratios, generic option clauses). Forcing every clause into technical/
    financial/eligibility would silently mislabel the ones that don't
    belong to any of them; better to say so than guess."""
    result = classify(
        subject_text=text,
        references=[],
        verdict_options=["technical", "financial", "eligibility", "other"],
        instruction=(
            "ROLE: You are reviewing one bidder-facing RFP criterion for classification "
            "purposes.\n"
            "OBJECTIVE: Classify it into exactly one category, based on what it is fundamentally "
            "a condition ABOUT.\n"
            "DECISION RULES:\n"
            "- 'technical': the criterion is fundamentally about the product/service being "
            "procured itself -- its specifications, performance, configuration, or compliance "
            "with a technical standard.\n"
            "- 'financial': the criterion is fundamentally about money -- cost, pricing, payment "
            "terms, or the bidder's financial capacity, deposits, or guarantees.\n"
            "- 'eligibility': the criterion is fundamentally about who is allowed to bid -- the "
            "bidder's own legal/business status, experience, or registrations/certifications "
            "required to participate, as opposed to a specification of the product or service "
            "itself.\n"
            "- 'other': the criterion is fundamentally about something else -- process, "
            "logistics, or administration of the tender itself, rather than the product, money, "
            "or the bidder's qualification to participate.\n"
            "- Classify by what the criterion is fundamentally a condition about, not by an "
            "incidental word it happens to contain -- a clause can mention a number or a "
            "document in passing while still fundamentally belonging to a different category.\n"
            "- Use 'other' honestly when a criterion genuinely does not fit the first three, "
            "rather than forcing a poor fit."
        ),
    )
    return result.verdict


def _extract_gem_bid_number(pdf_path: Path) -> str | None:
    """Returns None if not found -- not every RFP uploaded to this platform
    will necessarily be a real, already-published GeM listing (e.g. a buyer
    drafting a brand-new tender that only exists here first), so a missing
    bid number is a legitimate outcome, not an error."""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            match = _GEM_BID_NUMBER_PATTERN.search(text)
            if match:
                return match.group(0)
    return None


def _find_table_value(tables: list[PageTable], *label_keywords: str) -> str | None:
    """Scans every extracted table's rows for a cell whose (whitespace-
    normalized, lowercased) text contains all of label_keywords, and returns
    the next non-empty cell in that same row -- GeM's bilingual "Bid
    Details" table is consistently a label cell followed by its value cell.

    Table-aware, not text-position-based: a prior version of this project
    searched for an exact label phrase in pdfplumber's flattened
    extract_text() output instead, which broke on a real RFP whose
    bilingual column layout interleaved unrelated content mid-phrase
    ("Document required" / "supporting document" / "from seller" ended up
    non-contiguous). find_tables() has already resolved row/column
    boundaries by this point, so the label and its value are always exactly
    two adjacent cells regardless of how a given document's layout would
    have linearized in plain text -- this is the one fix meant to cover
    every "Bid Details" field this project reads, not a per-document patch."""
    for table in tables:
        for row in table.rows:
            for i, cell in enumerate(row):
                if not cell:
                    continue
                normalized = re.sub(r"\s+", " ", cell).strip().lower()
                if all(kw in normalized for kw in label_keywords):
                    for value in row[i + 1 :]:
                        if value and value.strip():
                            return value
    return None


def _extract_required_documents(tables: list[PageTable]) -> list[str]:
    """GeM's bilingual "Bid Details" table lists the document TYPES a bidder
    must submit (e.g. "Experience Criteria", "Past Performance") as one
    comma-separated cell value. This is a *different* check from criteria
    extraction above: it's "did the bidder submit the right document types
    at all" (a fast presence check, done at bid-check time by
    check_document_completeness.py), not "does the content satisfy a
    requirement" (that's retrieve_and_extract_evidence.py's job).

    Returns [] if no matching row is found at all (RFP templates may phrase
    this differently, or genuinely not state one)."""
    value = _find_table_value(tables, "document", "required")
    if value is None:
        return []

    end_idx = value.find("*In case any bidder")
    segment = value[:end_idx] if end_idx != -1 else value
    segment = re.sub(r"\s+", " ", segment).strip()

    items = [re.sub(r"\s+", " ", x).strip() for x in segment.split(",")]
    return [x for x in items if x]


def _extract_prohibited_practices(pdf_path: Path) -> list[str]:
    """GeM bid PDFs end with a standard disclaimer: a numbered list of
    buyer drafting-mistakes ("Incorporating any clause against MSME
    policy...", "Asking for any Tender fee...") that void the bid if
    present -- guidance for the BUYER, not a bidder requirement. This used
    to be filtered per-chunk during criteria extraction (see
    _is_guidance_text), which was genuinely unreliable for this specific
    list: judged in isolation, without the surrounding "these are things
    the buyer must NOT do" framing, several of these sentences read like
    plausible real requirements even to an LLM. Extracting the whole list
    once, as its own field, sidesteps the ambiguity entirely -- and lets
    check_prohibited_practices.py check the RFP's OWN criteria against it,
    a genuinely new check, not just a classification fix.

    Confirmed against the real NIELIT PDF: the intro sentence ends on one
    page, the numbered list itself is entirely on the next -- spans two
    pages, unlike _extract_required_documents() above."""
    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""
        found_start = False
        for page in pdf.pages:
            text = page.extract_text() or ""
            if not found_start:
                match = _PROHIBITED_PRACTICES_START.search(text)
                if match is None:
                    continue
                found_start = True
                text = text[match.end():]
            full_text += text
            if _PROHIBITED_PRACTICES_END in full_text:
                break
        if not found_start:
            return []

        end_idx = full_text.find(_PROHIBITED_PRACTICES_END)
        segment = full_text[:end_idx] if end_idx != -1 else full_text
        parts = re.split(r"\n?\d+\.\s+", segment)
        items = [re.sub(r"\s+", " ", x).strip() for x in parts[1:]]  # parts[0] is leftover intro text
        return [x for x in items if x]


def _extract_evaluation_method(tables: list[PageTable]) -> str:
    """GeM's "Evaluation Method" field states how the buyer will pick a
    winner -- another "Bid Details" table row, same shape as
    _extract_required_documents() above. Confirmed against real RFPs as
    "Total value wise evaluation" -- GeM's own phrase for L1 (lowest total
    price wins). Defaults to L1 if no matching row is found or its value
    doesn't clearly say QCBS -- L1 is the only value seen in real documents
    so far, and was already this project's universal default before this
    extraction existed, so a missed/ambiguous match degrades to the
    existing safe behavior, not a new failure mode."""
    value = _find_table_value(tables, "evaluation method")
    if value is None:
        return "L1"
    if re.search(r"QCBS|Quality\s+and\s+Cost", value, re.IGNORECASE):
        return "QCBS"
    return "L1"


# GeM's standard MSE purchase-preference paragraph (citing OM No.
# F.1/4/2021-PPD) states two RFP-specific numbers in sequence, both
# formatted as "N% (Selected by Buyer)" -- confirmed against the real RFP
# text: the price band a non-L1 MSE bidder must be within to get a
# price-match offer ("L-1+ 15% (Selected by Buyer)"), then the percentage
# of quantity awarded if they take it ("25% (selected by Buyer) percentage
# of total quantity"). Case varies between the two ("Selected"/"selected"
# in the real document), hence re.IGNORECASE.
_MSE_PRICE_BAND_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*\(selected by buyer\)", re.IGNORECASE)


def _extract_mse_preference_params(pdf_path: Path) -> tuple[float | None, float | None]:
    """Returns (price_band_percent, mse_share_percent), or (None, None) if
    the paragraph isn't found or doesn't match this exact two-number
    pattern -- not every RFP necessarily overrides the general 2012 Policy
    Order default with its own numbers, and guessing at a value nobody
    stated would be worse than leaving it unset (score_stage2 already
    handles a None here gracefully, skipping the price-match calculation
    rather than guessing)."""
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    matches = _MSE_PRICE_BAND_PATTERN.findall(full_text)
    if len(matches) >= 2:
        return float(matches[0]), float(matches[1])
    return None, None


def _normalize_for_matching(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _matches_prohibited_practice(chunk_text: str, prohibited_practices: list[str]) -> bool:
    """Deterministic exclusion, not an LLM guess -- chunk_text and the
    extracted prohibited_practices items come from the exact same
    underlying PDF text, just segmented slightly differently (the chunk
    keeps its clause number prefix, the extracted item doesn't), so a
    normalized substring match is reliable here, unlike the general
    guidance-vs-criterion judgment call."""
    norm_chunk = _normalize_for_matching(chunk_text)
    for practice in prohibited_practices:
        norm_practice = _normalize_for_matching(practice)
        if norm_practice and (norm_practice in norm_chunk or norm_chunk in norm_practice):
            return True
    return False


def extract_rfp_criteria(pdf_path: Path, rfp_id: str) -> StructuredRFP:
    logger.info("extract_rfp_criteria(rfp_id=%r) starting for %s", rfp_id, pdf_path.name)
    pages = extract_text_by_page(pdf_path)
    pages = [PageText(p.page_number, filter_english(p.text)) for p in pages]
    tables = extract_tables_by_page(pdf_path)
    chunks = chunk_document(pages, tables)

    prohibited_practices = _extract_prohibited_practices(pdf_path)

    candidates = [
        (i, c) for i, c in enumerate(chunks)
        if c.chunk_type == "prose" and c.clause_ref is not None and len(c.text.split()) >= _MIN_WORDS
        and not _matches_prohibited_practice(c.text, prohibited_practices)
    ]
    total = len(candidates)
    logger.info(
        "%d candidate clauses to classify (of %d total chunks, %d excluded as the RFP's own "
        "prohibited-practices list), up to %d concurrent LLM calls",
        total, len(chunks), len(prohibited_practices), _MAX_CONCURRENT_LLM_CALLS,
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_CONCURRENT_LLM_CALLS) as pool:
        # Stage 1: guidance-vs-criterion for every candidate, fanned out together.
        guidance_tasks = [functools.partial(_is_guidance_text, c.text) for _, c in candidates]
        is_guidance = _run_concurrent(pool, guidance_tasks, "stage 1/3 (guidance check)")

        accepted = [(i, c) for (i, c), g in zip(candidates, is_guidance) if not g]
        logger.info("stage 1/3 done: %d accepted as criteria, %d skipped as guidance",
                    len(accepted), total - len(accepted))

        # Stage 2: mandatory + category, only for accepted candidates. Both
        # checks per candidate are independent of each other too, so they're
        # combined into one task list -- interleaved in the same bounded
        # pool, not run as two back-to-back batches -- then split apart by
        # position afterward (every even index is mandatory, odd is category).
        logger.info("stage 2/3: mandatory + category check for %d criteria", len(accepted))
        stage2_tasks = []
        for _, c in accepted:
            stage2_tasks.append(functools.partial(_infer_mandatory, c.text))
            stage2_tasks.append(functools.partial(_infer_category, c.text))
        stage2_results = _run_concurrent(pool, stage2_tasks, "stage 2/3 (mandatory+category check)")
        mandatory_results = stage2_results[0::2]
        category_results = stage2_results[1::2]
        logger.info("stage 2/3 done")

        # Stage 3: infer a scoring rule (backend/models/rule.py) for each
        # accepted criterion that landed in a scored category -- eligibility
        # criteria are gate-only (score_stage1 never weighs them), so
        # skipping them avoids guaranteed-empty LLM calls. Needs Stage 2's
        # category_results, so it can't run concurrently with Stage 2 itself,
        # but every criterion's rule inference is independent of every
        # other's, so they're still fanned out together across the same
        # bounded pool as Stages 1-2. Most criteria won't have an explicit
        # rule (infer_rule() returns None) -- a common, expected outcome, not
        # an error; those criteria just keep scoring from their verdict
        # exactly as they did before rules existed (see score_stage1()).
        rule_indices = [idx for idx, category in enumerate(category_results) if category in SCORED_CATEGORIES]
        logger.info("stage 3/3: scoring-rule inference for %d of %d criteria (scored categories only)",
                    len(rule_indices), len(accepted))
        rule_tasks = [functools.partial(infer_rule, accepted[idx][1].text) for idx in rule_indices]
        rule_results = _run_concurrent(pool, rule_tasks, "stage 3/3 (scoring-rule inference)")
        rules_by_index = dict(zip(rule_indices, rule_results))
        logger.info("stage 3/3 done: %d rule(s) extracted", sum(1 for r in rule_results if r is not None))

    criteria = [
        Criterion(
            id=f"{rfp_id}_c{i}",
            text=chunk.text,
            mandatory=mandatory,
            category=category,
            page_number=chunk.page_number,
            clause_ref=chunk.clause_ref,
            rule=rules_by_index.get(idx),
        )
        for idx, ((i, chunk), mandatory, category) in enumerate(zip(accepted, mandatory_results, category_results))
    ]

    required_documents = _extract_required_documents(tables)
    gem_bid_number = _extract_gem_bid_number(pdf_path)
    evaluation_method = _extract_evaluation_method(tables)
    price_band_percent, mse_share_percent = _extract_mse_preference_params(pdf_path)
    logger.info(
        "extract_rfp_criteria(rfp_id=%r) done: %d criteria, %d required documents, "
        "%d prohibited practices, gem_bid_number=%r, evaluation_method=%r, "
        "price_band_percent=%r, mse_share_percent=%r",
        rfp_id, len(criteria), len(required_documents), len(prohibited_practices), gem_bid_number,
        evaluation_method, price_band_percent, mse_share_percent,
    )

    return StructuredRFP(
        rfp_id=rfp_id, source_file=pdf_path.name, criteria=criteria,
        required_documents=required_documents, prohibited_practices=prohibited_practices,
        gem_bid_number=gem_bid_number, evaluation_method=evaluation_method,
        price_band_percent=price_band_percent, mse_share_percent=mse_share_percent,
    )


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/rfps/Gem Bid Document.pdf")
    result = extract_rfp_criteria(path, rfp_id="test-rfp-1")
    print(f"{len(result.criteria)} criteria extracted from {path.name}")
    print(f"{len(result.required_documents)} required document types: {result.required_documents}")
    print(f"{len(result.prohibited_practices)} prohibited practices: {result.prohibited_practices}\n")
    for c in result.criteria:
        print(f"[{c.clause_ref}] mandatory={c.mandatory} category={c.category} (page {c.page_number})")
        print(f"  {c.text[:150]}")
        print(f"  rule={c.rule!r}")
        print()
