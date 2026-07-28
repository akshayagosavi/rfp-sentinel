"""
M11: retrieve_and_extract_evidence() -- for every criterion the buyer
approved, decide whether a bidder's Packet-I (technical) content satisfies
it. Same pattern as check_rfp_compliance (M9): search -> classify via the
LLM, just pointed at a bid instead of the norms knowledge base. Criteria
drive the loop (not bid content) -- see the plan's Bid Evaluation Design
section for why: it guarantees every criterion gets checked, bounds the
number of LLM calls to the criteria count, and makes "not_found" a real,
distinct signal instead of a silent gap.

A deterministic regex-based threshold checker used to run before the LLM
here (see check_rfp_compliance.py's docstring for why it existed and why
it was removed); this module now goes straight to the LLM classifier.

Packet-II (financial) is never searched here -- search_bid() defaults to
packet="I", enforcing the GFR Rule 189 seal structurally, not by convention.

Milestone 7 of the rule-based scoring redesign: compliance (the mandatory
gate) and scoring (marks earned, when a criterion has a Rule -- see
backend/models/rule.py) are independent concepts, evaluated via one of three
paths per criterion, never two independent LLM calls interpreting the same
evidence separately (that can silently disagree -- caught during design
review):
  - `rule is None`: today's exact classify() flow, unchanged.
  - `rule is not None` and not mandatory: no gate applies, so only a value is
    needed -- extract_criterion_value() + score_value().
  - `rule is not None` and mandatory: one merged call,
    extract_value_and_compliance(), answering both the compliance judgment
    and the rule's value from a single reading of the same evidence.
"""
import sys
from pathlib import Path

from backend.llm.ollama_client import ReferenceChunk, classify, extract_json
from backend.logging_config import get_logger
from backend.models.evidence import EvidenceItem
from backend.models.rfp import StructuredRFP
from backend.models.rule import Rule
from backend.rag.embeddings import embed_text
from backend.rag.qdrant_client import get_client, search_bid
from backend.scoring.criterion_evaluator import score_value

logger = get_logger(__name__)

_VERDICT_OPTIONS = ["pass", "fail", "partial"]
_INSTRUCTION = (
    "ROLE: You are evaluating a bidder's submitted content against one specific RFP criterion.\n"
    "OBJECTIVE: Decide whether the referenced bid content satisfies the criterion below.\n"
    "DECISION RULES:\n"
    "- Classify 'pass' if the referenced content fully satisfies what the criterion requires.\n"
    "- Classify 'fail' if the referenced content actively contradicts the criterion, or clearly "
    "falls short of what it requires.\n"
    "- Classify 'partial' if the referenced content addresses the criterion but incompletely, "
    "with caveats, or only partly meets it.\n"
    "- These three options are meant to cover every real case -- choose the closest even if "
    "none feels like a perfect fit.\n"
    "- If the referenced content does not actually address this specific criterion at all, set "
    "reference_index to null regardless of which of the three verdict words you chose above -- "
    "that null, not the verdict word, is what signals 'not relevant' downstream."
)

_SEMANTIC_MATCH_NOTE = (
    "The bidder may describe this using different wording than the criterion itself (e.g. a "
    "specific job title or paraphrase instead of the exact term used) -- interpret semantically "
    "equivalent content, not just an exact keyword match."
)


def extract_criterion_value(
    rule: Rule, criterion_text: str, references: list[ReferenceChunk]
) -> tuple[float | str | None, dict | None]:
    """Used when a criterion has a rule but isn't mandatory -- no compliance
    gate applies, so only rule.field's value is needed. Returns (value,
    citation); value is None whenever the referenced content doesn't
    actually state it, or the extraction is uncited -- same "don't guess"
    grounding discipline classify() already applies to verdicts below."""
    instruction = (
        f"ROLE: You are extracting one specific value from a bidder's submitted content, "
        f"relative to an RFP criterion.\n"
        f'OBJECTIVE: Extract the value of "{rule.field}" as required by the criterion below, '
        f"from the referenced bid content.\n"
        f"DECISION RULES:\n"
        f"- {_SEMANTIC_MATCH_NOTE}\n"
        f'- Respond with {{"value": <the extracted number or short string>}} under "data".\n'
        f'- Respond with {{"value": null}} under "data" if the referenced content does not '
        f"actually state this value."
    )
    result = extract_json(subject_text=criterion_text, instruction=instruction, references=references)
    value = result.data.get("value")
    if value is None or result.citation is None:
        return None, None
    return value, result.citation


def extract_value_and_compliance(
    criterion_text: str, rule: Rule, references: list[ReferenceChunk]
) -> tuple[str | None, float | str | None, dict | None]:
    """Used when a criterion is BOTH mandatory and has a rule (uncommon --
    e.g. "5+ years mandatory, more years = more marks"). One merged call
    answering the compliance judgment AND rule.field's value from a single
    reading of the same evidence, so the two can't disagree about what the
    evidence actually says -- unlike calling classify() and
    extract_criterion_value() independently, which could. Returns
    (verdict, value, citation); verdict is None if the model's answer wasn't
    one of _VERDICT_OPTIONS or the extraction was uncited."""
    instruction = (
        f"ROLE: You are evaluating a bidder's submitted content against one specific RFP "
        f"criterion, and extracting a scored value from the same evidence in the same pass.\n"
        f"OBJECTIVE: From the same referenced bid content, decide (1) whether the bid satisfies "
        f'the criterion below, and (2) what value "{rule.field}" takes as described or implied '
        f"by the criterion.\n"
        f"DECISION RULES:\n"
        f'- For (1), answer with exactly one of "pass" (fully satisfied), "fail" (actively '
        f'contradicts or clearly fails to meet it), or "partial" (addressed but incompletely).\n'
        f"- For (2), {_SEMANTIC_MATCH_NOTE}\n"
        f"- Base both answers on the same single reading of the evidence -- the value you "
        f"extract and the verdict you choose must be consistent with each other, not "
        f"independently guessed.\n"
        f'- Respond with {{"verdict": "pass"|"fail"|"partial", "value": <the extracted number or '
        f'short string, or null if not stated>}} under "data".'
    )
    result = extract_json(subject_text=criterion_text, instruction=instruction, references=references)
    verdict = result.data.get("verdict")
    if verdict not in _VERDICT_OPTIONS or result.citation is None:
        return None, None, None
    return verdict, result.data.get("value"), result.citation


def _evaluate_via_classify(criterion, bid_id: str, references: list[ReferenceChunk], n: int, total: int) -> EvidenceItem:
    """rule is None -- today's exact flow, byte-for-byte unchanged."""
    try:
        result = classify(
            subject_text=criterion.text, references=references,
            verdict_options=_VERDICT_OPTIONS, instruction=_INSTRUCTION,
        )
    except RuntimeError as e:
        logger.warning("criterion %d/%d: classify() failed (%s) -- not_found", n, total, e)
        return EvidenceItem(
            criterion_id=criterion.id, bid_id=bid_id, verdict="not_found",
            reasoning=f"Classifier could not produce a usable verdict: {e}",
        )

    if result.citation is None:
        logger.info("criterion %d/%d: verdict=%s but uncited -- downgraded to not_found", n, total, result.verdict)
        return EvidenceItem(
            criterion_id=criterion.id, bid_id=bid_id, verdict="not_found",
            reasoning="Relevant content was retrieved but the model could not ground a verdict in it.",
        )

    logger.info("criterion %d/%d: verdict=%s (cited)", n, total, result.verdict)
    return EvidenceItem(
        criterion_id=criterion.id, bid_id=bid_id, verdict=result.verdict,
        reasoning=result.reasoning, citation=result.citation,
    )


def _evaluate_rule_only(criterion, bid_id: str, references: list[ReferenceChunk], n: int, total: int) -> EvidenceItem:
    """rule is not None and not mandatory -- no gate applies, only a value/
    score is needed. verdict here is a coarse presence indicator only
    ("pass" if a value was extracted, "not_found" if not) -- NOT a
    compliance judgment; the real signal is rule_result, consumed by
    score_stage1()'s weighted aggregation instead of VERDICT_SCORE."""
    try:
        value, citation = extract_criterion_value(criterion.rule, criterion.text, references)
    except RuntimeError as e:
        logger.warning("criterion %d/%d: extract_criterion_value() failed (%s) -- not_found", n, total, e)
        value, citation = None, None

    rule_result = score_value(criterion.rule, value)
    verdict = "pass" if value is not None else "not_found"
    logger.info(
        "criterion %d/%d: rule-scored (%s), value=%r score=%s/%s",
        n, total, criterion.rule.type, value, rule_result.score, rule_result.max_score,
    )
    return EvidenceItem(
        criterion_id=criterion.id, bid_id=bid_id, verdict=verdict,
        reasoning=f"Extracted {criterion.rule.field}={value!r}; matched {rule_result.matched.kind}.",
        citation=citation, rule_result=rule_result.model_dump(),
    )


def _evaluate_mandatory_rule(criterion, bid_id: str, references: list[ReferenceChunk], n: int, total: int) -> EvidenceItem:
    """rule is not None and mandatory -- one merged extraction answers both
    the gate and the score from a single reading of the evidence."""
    try:
        verdict, value, citation = extract_value_and_compliance(criterion.text, criterion.rule, references)
    except RuntimeError as e:
        logger.warning("criterion %d/%d: extract_value_and_compliance() failed (%s) -- not_found", n, total, e)
        verdict, value, citation = None, None, None

    if verdict is None:
        logger.info("criterion %d/%d: merged extraction ungrounded/invalid -- not_found", n, total)
        return EvidenceItem(
            criterion_id=criterion.id, bid_id=bid_id, verdict="not_found",
            reasoning="Relevant content was retrieved but the model could not ground a verdict/value in it.",
        )

    rule_result = score_value(criterion.rule, value)
    logger.info(
        "criterion %d/%d: mandatory+rule (%s), verdict=%s value=%r score=%s/%s",
        n, total, criterion.rule.type, verdict, value, rule_result.score, rule_result.max_score,
    )
    return EvidenceItem(
        criterion_id=criterion.id, bid_id=bid_id, verdict=verdict,
        reasoning=f"Extracted {criterion.rule.field}={value!r}; matched {rule_result.matched.kind}.",
        citation=citation, rule_result=rule_result.model_dump(),
    )


def retrieve_and_extract_evidence(
    bid_id: str, structured_rfp: StructuredRFP, criterion_vectors: dict[str, list[float]] | None = None,
) -> list[EvidenceItem]:
    """criterion_vectors: optional {criterion_id: embedding} map, computed
    once by the caller (run_stage1_evaluation, across the whole RFP) and
    reused for every bid -- avoids re-embedding the same, unchanged
    criterion text once per bid. Embeddings are deterministic (same text
    always produces the same vector), so this changes nothing about what
    gets found or classified, only how many times identical work is redone.
    Optional and defaulting to None (computing on the fly, exactly as
    before) so this function still works standalone, e.g. from its own
    __main__ block below, without every caller needing to build the map."""
    client = get_client()
    evidence = []
    total = len(structured_rfp.criteria)
    logger.info("retrieve_and_extract_evidence(bid_id=%r) starting: %d criteria", bid_id, total)

    for n, criterion in enumerate(structured_rfp.criteria, start=1):
        logger.info("criterion %d/%d (clause %s): searching bid Packet-I", n, total, criterion.clause_ref)
        if criterion_vectors is not None:
            query_vector = criterion_vectors[criterion.id]
        else:
            query_vector = embed_text(criterion.text)
        matches = search_bid(client, query_vector, bid_id=bid_id, packet="I", top_k=5)

        if not matches:
            logger.info("criterion %d/%d: no bid matches -- not_found", n, total)
            evidence.append(EvidenceItem(
                criterion_id=criterion.id,
                bid_id=bid_id,
                verdict="not_found",
                reasoning="No relevant content found in the bidder's Packet-I (technical) documents.",
            ))
            continue

        references = [
            ReferenceChunk(
                text=m.payload["text"],
                citation={
                    "source_file": m.payload["source_file"],
                    "page_number": m.payload["page_number"],
                    "clause_ref": m.payload.get("clause_ref"),
                },
            )
            for m in matches
        ]

        if criterion.rule is None:
            item = _evaluate_via_classify(criterion, bid_id, references, n, total)
        elif criterion.mandatory:
            item = _evaluate_mandatory_rule(criterion, bid_id, references, n, total)
        else:
            item = _evaluate_rule_only(criterion, bid_id, references, n, total)
        evidence.append(item)

    logger.info("retrieve_and_extract_evidence(bid_id=%r) done", bid_id)
    return evidence


if __name__ == "__main__":
    from backend.graph.extract_rfp_criteria import extract_rfp_criteria

    rfp_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/rfps/47887e14_Gem Bid Document.pdf")
    bid_id = sys.argv[2] if len(sys.argv) > 2 else "4670f967"
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 6  # keep it fast -- first N criteria only

    rfp = extract_rfp_criteria(rfp_path, rfp_id="test-rfp-1")
    rfp.criteria = rfp.criteria[:n]

    evidence = retrieve_and_extract_evidence(bid_id, rfp)

    by_verdict: dict[str, int] = {}
    for e in evidence:
        by_verdict[e.verdict] = by_verdict.get(e.verdict, 0) + 1
    print(f"{len(evidence)} criteria checked against bid_id={bid_id!r}")
    print(f"verdict counts: {by_verdict}\n")

    criteria_by_id = {c.id: c for c in rfp.criteria}
    for e in evidence:
        criterion_text = criteria_by_id[e.criterion_id].text[:100]
        print(f"[{e.verdict.upper()}] {criterion_text}")
        print(f"  reasoning: {e.reasoning}")
        if e.citation:
            print(f"  citation: {e.citation}")
        if e.rule_result:
            print(f"  rule_result: {e.rule_result}")
        print()
