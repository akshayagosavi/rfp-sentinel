"""
Runs once an RFP closes (via the closing_date timer or the buyer's manual
"Close & Evaluate Now" override) -- Stage 1 only (technical gate). For every
submitted bid: retrieve_and_extract_evidence() against the buyer-approved
criteria (Packet-I / technical documents only -- GFR Rule 189's seal is
enforced by search_bid() defaulting to packet="I", not by convention here),
persist the full per-criterion verdict trail, then score_stage1() to gate
pass/fail and compute a technical_score.

Stage 2 (financial ranking) is deliberately NOT run here -- it needs a price
extracted from the bidder's sealed financial document (Packet-II), which
isn't built yet (tracked in ROADMAP.md). This module only takes an RFP as
far as "who passed the technical gate," not "who wins."

Not a LangGraph node -- unlike extract_rfp_criteria/check_rfp_compliance,
this runs per-bid against data that lives in Postgres (bids table), not in
the graph's own checkpointed state, and there's no human-in-the-loop pause
partway through it. A plain function invoked from a background task is a
better fit than forcing it into the graph.
"""
from backend.db import (
    list_bid_ids_for_rfp,
    mark_bid_under_evaluation,
    save_bid_evidence,
    save_stage1_result,
)
from backend.graph.retrieve_and_extract_evidence import retrieve_and_extract_evidence
from backend.logging_config import get_logger
from backend.models.rfp import StructuredRFP
from backend.scoring.scoring import score_stage1

logger = get_logger(__name__)


def run_stage1_evaluation(pool, rfp_id: str, structured_rfp: StructuredRFP) -> None:
    bid_ids = list_bid_ids_for_rfp(pool, rfp_id)
    logger.info("run_stage1_evaluation(rfp_id=%r): %d bid(s) to evaluate", rfp_id, len(bid_ids))

    for bid_id in bid_ids:
        try:
            mark_bid_under_evaluation(pool, bid_id)
            evidence = retrieve_and_extract_evidence(bid_id, structured_rfp)
            save_bid_evidence(pool, bid_id, [e.model_dump() for e in evidence])
            result = score_stage1(structured_rfp.criteria, evidence)
            save_stage1_result(pool, bid_id, result.model_dump())
            logger.info(
                "bid %r: passed=%s technical_score=%s failed=%d pending=%d",
                bid_id, result.passed, result.technical_score,
                len(result.failed_criteria), len(result.pending_criteria),
            )
        except Exception:
            logger.exception("Stage 1 evaluation failed for bid %r (rfp_id=%r)", bid_id, rfp_id)

    logger.info("run_stage1_evaluation(rfp_id=%r) done", rfp_id)
