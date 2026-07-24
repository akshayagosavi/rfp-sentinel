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
"""
import sys
from pathlib import Path

from backend.llm.ollama_client import ReferenceChunk, classify
from backend.logging_config import get_logger
from backend.models.rfp import StructuredRFP

logger = get_logger(__name__)

_VERDICT_OPTIONS = ["compliant", "violation", "unclear"]
_INSTRUCTION = (
    "The reference material is GeM's own list of buyer drafting-mistakes that void a bid if "
    "present in the RFP. Does the criterion below actually do one of the things a reference "
    "item describes? Classify it as 'violation' ONLY if the criterion's own content matches "
    "one of the listed practices. If none of the reference items describe anything this "
    "criterion actually does, that is 'unclear', not 'violation' -- most criteria won't match "
    "any of these, and that's the expected, normal outcome."
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
            criterion.prohibited_practice_issue = result.reasoning
            criterion.prohibited_practice_citation = result.citation
            logger.info("criterion %d/%d: FLAGGED -- %s", n, total, result.reasoning)
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
