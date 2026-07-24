"""
M9: check_rfp_compliance() -- for every extracted criterion, decide whether
it conflicts with government norms, before the buyer sees the RFP as final.

Classifies via the LLM (backend/llm/ollama_client.py). A deterministic
regex-based threshold checker used to run first here, added at M8 because
Llama 3.2 3B reliably got numeric threshold comparisons backwards; removed
after switching to a larger remote model (qwen2.5:7b) that was confirmed,
via a direct side-by-side rerun of the exact M8 test case, to get the same
comparisons right without it.
"""
import sys
from pathlib import Path

from backend.llm.ollama_client import ReferenceChunk, classify
from backend.logging_config import get_logger
from backend.models.rfp import Criterion, StructuredRFP
from backend.rag.embeddings import embed_text
from backend.rag.qdrant_client import get_client, search_active

logger = get_logger(__name__)

_VERDICT_OPTIONS = ["compliant", "violation", "unclear"]
_INSTRUCTION = (
    "Does the criterion below conflict with the referenced government norm clause(s)? "
    "Classify it as compliant, violation, or unclear. "
    "Use 'violation' ONLY if the reference material describes a requirement that directly "
    "contradicts or is incompatible with the criterion. If the reference material simply does "
    "not mention this specific criterion at all, that is 'unclear', not 'violation' -- the "
    "absence of a matching rule is not the same as breaking one."
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
            criterion.compliance_issue = result.reasoning
            criterion.compliance_citation = result.citation
            logger.info("criterion %d/%d: FLAGGED -- %s", n, total, result.reasoning)
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
