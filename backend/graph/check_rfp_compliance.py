"""
M9: check_rfp_compliance() -- for every extracted criterion, decide whether
it conflicts with government norms, before the buyer sees the RFP as final.

Classifies via the LLM (backend/llm/ollama_client.py). A deterministic
regex-based threshold checker used to run first here, added at M8 because
Llama 3.2 3B reliably got numeric threshold comparisons backwards; removed
after switching to a larger remote model (qwen2.5:7b) that was confirmed,
via a direct side-by-side rerun of the exact M8 test case, to get the same
comparisons right without it.

A "violation" verdict is never surfaced on its own -- it must additionally
survive confirm_violation()'s adversarial second pass (backend/llm/
ollama_client.py) before becoming a flag. Added after repeatedly finding
real false positives here across multiple, unrelated real RFPs (a
self-deferring ATC clause, a conflict-of-interest clause restating GeM's
own related-bidder rule almost verbatim) -- the single classify() call
kept mistaking "the criterion restates/aligns with the reference" for "the
criterion contradicts it," and prompt-wording fixes reduced but never
eliminated this, recurring on a new clause topic each time. See
confirm_violation()'s own docstring for why a second, skeptical pass is
the chosen mitigation over further wording iteration.
"""
import sys
from pathlib import Path

from backend.llm.ollama_client import ReferenceChunk, classify, confirm_violation
from backend.logging_config import get_logger
from backend.models.rfp import Criterion, StructuredRFP
from backend.rag.embeddings import embed_text
from backend.rag.qdrant_client import get_client, search_active

logger = get_logger(__name__)

_VERDICT_OPTIONS = ["compliant", "violation", "unclear"]
_INSTRUCTION = (
    "ROLE: You are checking a single RFP criterion for conflict with retrieved government "
    "procurement norm clauses.\n"
    "OBJECTIVE: Decide whether the criterion is compliant, in violation, or unclear relative "
    "to the reference norms.\n"
    "DECISION RULES:\n"
    "- Classify 'violation' only when a specific reference clause states a rule that this "
    "criterion's own content directly contradicts or is incompatible with -- i.e. following "
    "the criterion as written would require breaking what that reference actually mandates or "
    "prohibits.\n"
    "- A reference clause that discusses a related or general topic, sets broader context, or "
    "describes a general accountability/process framework -- without stating a specific rule "
    "this criterion's specific content actually breaks -- does not support 'violation'. "
    "Distinguish 'this reference is about the same general area' from 'this reference states a "
    "rule this criterion actually breaks'.\n"
    "- If the criterion's own wording already defers to applicable norms (e.g. it states it "
    "applies 'subject to' or 'unless otherwise permitted by' the governing rules), that "
    "deference is not itself a violation -- check whether the reference actually forbids what "
    "the criterion does, not merely whether the criterion acknowledges that norms exist.\n"
    "- If no reference clause specifically addresses this criterion's particular requirement, "
    "classify 'unclear'."
)


def check_rfp_compliance(structured_rfp: StructuredRFP) -> StructuredRFP:
    client = get_client()
    total = len(structured_rfp.criteria)
    logger.info("check_rfp_compliance(rfp_id=%r) starting: %d criteria", structured_rfp.rfp_id, total)

    for n, criterion in enumerate(structured_rfp.criteria, start=1):
        logger.info("criterion %d/%d (clause %s): searching norms", n, total, criterion.clause_ref)
        query_vector = embed_text(criterion.text)
        matches = search_active(client, query_vector, top_k=5)
        if not matches:
            logger.info("criterion %d/%d: no norm matches -- left unflagged", n, total)
            continue  # nothing relevant found -- leave unflagged, not a false violation

        references = [
            ReferenceChunk(
                text=m.payload["text"],
                citation={
                    "norm_name": m.payload["norm_name"],
                    "clause_ref": m.payload.get("clause_ref"),
                    "page_number": m.payload["page_number"],
                },
            )
            for m in matches
        ]

        result = classify(
            subject_text=criterion.text,
            references=references,
            verdict_options=_VERDICT_OPTIONS,
            instruction=_INSTRUCTION,
        )
        # An uncited "violation" isn't a grounded finding -- it's the model
        # guessing without support from the retrieved norm text. Never
        # surface a compliance flag that can't be traced to a real citation.
        if result.verdict == "violation" and result.citation is not None:
            matched_ref = next((r for r in references if r.citation == result.citation), None)
            challenge = confirm_violation(criterion.text, matched_ref, result.reasoning) if matched_ref else None
            if challenge is not None and challenge.verdict == "confirmed":
                criterion.compliance_issue = result.reasoning
                criterion.compliance_citation = result.citation
                logger.info("criterion %d/%d: FLAGGED (confirmed) -- %s", n, total, result.reasoning)
            else:
                logger.info(
                    "criterion %d/%d: violation NOT confirmed on challenge (%s) -- not flagged",
                    n, total, challenge.reasoning if challenge else "no matching reference",
                )
        else:
            logger.info("criterion %d/%d: verdict=%s -- not flagged", n, total, result.verdict)

    logger.info("check_rfp_compliance(rfp_id=%r) done", structured_rfp.rfp_id)
    return structured_rfp


if __name__ == "__main__":
    from backend.graph.extract_rfp_criteria import extract_rfp_criteria

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/rfps/Gem Bid Document.pdf")
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 6  # keep it fast -- first N criteria only

    rfp = extract_rfp_criteria(path, rfp_id="test-rfp-1")
    rfp.criteria = rfp.criteria[:n]
    rfp = check_rfp_compliance(rfp)

    flagged = [c for c in rfp.criteria if c.compliance_issue]
    print(f"{len(rfp.criteria)} criteria checked, {len(flagged)} flagged\n")
    for c in rfp.criteria:
        status = "FLAGGED" if c.compliance_issue else "ok"
        print(f"[{c.clause_ref}] {status}")
        if c.compliance_issue:
            print(f"  issue: {c.compliance_issue}")
            print(f"  citation: {c.compliance_citation}")
        print()
