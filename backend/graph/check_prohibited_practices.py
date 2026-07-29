"""
check_prohibited_practices() -- checks the RFP's own extracted criteria
against GeM's own list of buyer drafting-mistakes for THIS RFP (extracted
by extract_rfp_criteria.py's _extract_prohibited_practices(), e.g.
"Incorporating any clause against the MSME policy...", "Asking for any
Tender fee..."). If present, a clause matching one of these voids the bid
per GeM's own rules -- catching this before Checkpoint A means the buyer
finds out before publishing, not after a bidder complains or GeM rejects it.

Same pattern as check_rfp_compliance.py (search-free here, since the
prohibited-practices list is short and RFP-specific -- all of it fits
directly in one prompt as references, no Qdrant retrieval needed), and
the same citation-grounding discipline: a violation is only kept if the
model points at a specific listed practice, never an uncited guess.

Also the same second-pass discipline as check_rfp_compliance.py: a
"violation" verdict must additionally survive confirm_violation()'s
adversarial challenge (backend/llm/ollama_client.py) before becoming a
flag -- added after finding this exact classify() call flag a clause that
was itself just restating GeM's own related-bidder rule almost verbatim,
mistaking "matches the reference" for "contradicts it."
"""
import sys
from pathlib import Path

from backend.llm.ollama_client import ReferenceChunk, classify, confirm_violation
from backend.logging_config import get_logger
from backend.models.rfp import StructuredRFP

logger = get_logger(__name__)

_VERDICT_OPTIONS = ["compliant", "violation", "unclear"]
_INSTRUCTION = (
    "ROLE: You are checking a single RFP criterion against this RFP's own extracted list of "
    "buyer drafting practices that GeM prohibits (a bid is voided if any of these appear in the "
    "RFP).\n"
    "OBJECTIVE: Decide whether the criterion's own content actually performs one of the "
    "prohibited practices described in the reference material.\n"
    "DECISION RULES:\n"
    "- Classify 'violation' only if the criterion's own wording actually carries out the "
    "specific action a reference item describes -- not because the criterion and the reference "
    "item merely share a general subject, category, or vocabulary.\n"
    "- For each reference item, first identify the precise act it prohibits (what, specifically, "
    "would have to be present for that practice to occur). Then check whether the criterion's "
    "own text actually performs that precise act, as distinct from discussing the same general "
    "kind of thing, correctly citing a related rule, or stating a required attribute in "
    "generic, source-neutral terms.\n"
    "- Correctly and accurately referencing, quoting, or complying with an external rule or "
    "policy is not, by itself, a violation of a prohibition against misstating or contradicting "
    "that rule -- classify 'violation' for that kind of practice only if the criterion's own "
    "content actually gets the rule wrong or contradicts it.\n"
    "- Stating a required specification, capability, or attribute value in generic terms is not, "
    "by itself, the same as identifying a specific commercial source -- classify 'violation' for "
    "that kind of practice only if the criterion actually names or points to a specific "
    "supplier, maker, or source, rather than describing what's required without reference to "
    "any particular one.\n"
    "- Most criteria will not match any prohibited practice -- that is the normal, expected "
    "outcome. If none of the reference items describe an act the criterion actually performs, "
    "classify 'unclear'."
)


def check_prohibited_practices(structured_rfp: StructuredRFP) -> StructuredRFP:
    if not structured_rfp.prohibited_practices:
        logger.info("check_prohibited_practices(rfp_id=%r): no prohibited-practices list extracted, skipping",
                    structured_rfp.rfp_id)
        return structured_rfp

    references = [
        ReferenceChunk(text=p, citation={"prohibited_practice": p})
        for p in structured_rfp.prohibited_practices
    ]

    total = len(structured_rfp.criteria)
    logger.info("check_prohibited_practices(rfp_id=%r) starting: %d criteria against %d listed practices",
                structured_rfp.rfp_id, total, len(references))

    for n, criterion in enumerate(structured_rfp.criteria, start=1):
        result = classify(
            subject_text=criterion.text,
            references=references,
            verdict_options=_VERDICT_OPTIONS,
            instruction=_INSTRUCTION,
        )
        if result.verdict == "violation" and result.citation is not None:
            matched_ref = next((r for r in references if r.citation == result.citation), None)
            challenge = confirm_violation(criterion.text, matched_ref, result.reasoning) if matched_ref else None
            if challenge is not None and challenge.verdict == "confirmed":
                criterion.prohibited_practice_issue = result.reasoning
                criterion.prohibited_practice_citation = result.citation
                logger.info("criterion %d/%d: FLAGGED (confirmed) -- %s", n, total, result.reasoning)
            else:
                logger.info(
                    "criterion %d/%d: violation NOT confirmed on challenge (%s) -- not flagged",
                    n, total, challenge.reasoning if challenge else "no matching reference",
                )
        else:
            logger.info("criterion %d/%d: verdict=%s -- not flagged", n, total, result.verdict)

    logger.info("check_prohibited_practices(rfp_id=%r) done", structured_rfp.rfp_id)
    return structured_rfp


if __name__ == "__main__":
    from backend.graph.extract_rfp_criteria import extract_rfp_criteria

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/rfps/47887e14_Gem Bid Document.pdf")

    rfp = extract_rfp_criteria(path, rfp_id="test-rfp-1")
    rfp = check_prohibited_practices(rfp)

    flagged = [c for c in rfp.criteria if c.prohibited_practice_issue]
    print(f"{len(rfp.criteria)} criteria checked against {len(rfp.prohibited_practices)} prohibited practices")
    print(f"{len(flagged)} flagged\n")
    for c in rfp.criteria:
        status = "FLAGGED" if c.prohibited_practice_issue else "ok"
        print(f"[{c.clause_ref}] {status}")
        if c.prohibited_practice_issue:
            print(f"  issue: {c.prohibited_practice_issue}")
            print(f"  matched: {c.prohibited_practice_citation}")
        print()
