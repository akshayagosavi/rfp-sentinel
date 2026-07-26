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
"""
import sys
from pathlib import Path

from backend.llm.ollama_client import ReferenceChunk, classify
from backend.logging_config import get_logger
from backend.models.evidence import EvidenceItem
from backend.models.rfp import StructuredRFP
from backend.rag.embeddings import embed_text
from backend.rag.qdrant_client import get_client, search_bid

logger = get_logger(__name__)

_VERDICT_OPTIONS = ["pass", "fail", "partial"]
_INSTRUCTION = (
    "Does the referenced bid content satisfy the RFP criterion below? "
    "You must choose exactly one verdict word: pass (fully satisfied), fail (the bid "
    "content actively contradicts or clearly fails to meet it), or partial (addressed but "
    "incompletely, or with caveats) -- never any other word, even if none of them feel "
    "like a perfect fit. If the referenced content doesn't actually address this specific "
    "criterion at all, set reference_index to null regardless of which verdict word you "
    "picked -- that null, not the verdict word, is what signals 'not relevant' downstream."
)


def retrieve_and_extract_evidence(bid_id: str, structured_rfp: StructuredRFP) -> list[EvidenceItem]:
    client = get_client()
    evidence = []
    total = len(structured_rfp.criteria)
    logger.info("retrieve_and_extract_evidence(bid_id=%r) starting: %d criteria", bid_id, total)

    for n, criterion in enumerate(structured_rfp.criteria, start=1):
        logger.info("criterion %d/%d (clause %s): searching bid Packet-I", n, total, criterion.clause_ref)
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

        try:
            result = classify(
                subject_text=criterion.text,
                references=references,
                verdict_options=_VERDICT_OPTIONS,
                instruction=_INSTRUCTION,
            )
        except RuntimeError as e:
            # classify() exhausted its retries -- the model never produced a
            # valid verdict for this criterion (e.g. it emitted the literal
            # string "null" instead of one of _VERDICT_OPTIONS). Downgrading
            # to not_found here, not re-raising, matches the uncited-verdict
            # handling just below: an unusable answer isn't a finding, but it
            # also shouldn't cost the bid every other criterion's evidence.
            logger.warning("criterion %d/%d: classify() failed (%s) -- not_found", n, total, e)
            evidence.append(EvidenceItem(
                criterion_id=criterion.id,
                bid_id=bid_id,
                verdict="not_found",
                reasoning=f"Classifier could not produce a usable verdict: {e}",
            ))
            continue

        # Same grounding discipline as check_rfp_compliance: a verdict that
        # can't point at a real citation isn't a finding, it's a guess.
        if result.citation is not None:
            logger.info("criterion %d/%d: verdict=%s (cited)", n, total, result.verdict)
            evidence.append(EvidenceItem(
                criterion_id=criterion.id,
                bid_id=bid_id,
                verdict=result.verdict,
                reasoning=result.reasoning,
                citation=result.citation,
            ))
        else:
            logger.info("criterion %d/%d: verdict=%s but uncited -- downgraded to not_found", n, total, result.verdict)
            evidence.append(EvidenceItem(
                criterion_id=criterion.id,
                bid_id=bid_id,
                verdict="not_found",
                reasoning="Relevant content was retrieved but the model could not ground a verdict in it.",
            ))

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
        print()
