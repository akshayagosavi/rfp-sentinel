"""
Runs once the buyer explicitly opens Packet-II ("Open Financial Bids") for
an RFP that has finished Stage 1 -- only bidders who passed the technical
gate get their price extracted and ranked; a technically disqualified
bidder's financial document is never opened here, mirroring GFR Rule 189's
two-envelope principle (see extract_bid_price.py's docstring for why this
is a separate, buyer-triggered action rather than automatic).

Branches on structured_rfp.evaluation_method (extracted from the RFP's own
"Evaluation Method" field, see extract_rfp_criteria.py -- defaults to L1
if absent/ambiguous): L1 uses score_stage2() (price rank + MSE price-match,
using this RFP's own price_band_percent/mse_share_percent if it stated
them); QCBS uses score_stage2_qcbs() (technical_score + price blended into
one ranking). Neither branch guesses a missing number -- score_stage2()
just skips the price-match calculation if price_band_percent/
mse_share_percent are None, same "surface it, don't silently resolve it"
discipline used everywhere else in this project.
"""
from backend.db import get_stage1_results_for_rfp, save_bid_price, save_stage2_result
from backend.graph.extract_bid_price import extract_bid_price
from backend.logging_config import get_logger
from backend.models.rfp import StructuredRFP
from backend.scoring.scoring import BidInput, score_stage2, score_stage2_qcbs

logger = get_logger(__name__)


def run_stage2_evaluation(pool, rfp_id: str, structured_rfp: StructuredRFP) -> None:
    bids = get_stage1_results_for_rfp(pool, rfp_id)
    qualified = [b for b in bids if b["status"] == "stage1_passed"]
    logger.info(
        "run_stage2_evaluation(rfp_id=%r): %d Stage-1-qualified bid(s), evaluation_method=%r",
        rfp_id, len(qualified), structured_rfp.evaluation_method,
    )

    bid_inputs = []
    technical_scores = {}
    for b in qualified:
        result = extract_bid_price(b["bid_id"])
        if result.price is None:
            logger.warning(
                "bid %r: no price extracted (%s) -- excluded from ranking, needs human follow-up",
                b["bid_id"], result.reasoning,
            )
            continue
        save_bid_price(pool, b["bid_id"], result.price)
        bid_inputs.append(BidInput(
            bid_id=b["bid_id"], price=result.price, is_mii_local=b["is_mii_local"], is_mse=b["is_mse"],
        ))
        technical_scores[b["bid_id"]] = b["technical_score"] or 0.0
        logger.info("bid %r: extracted price=%s", b["bid_id"], result.price)

    if structured_rfp.evaluation_method == "QCBS":
        stage2 = score_stage2_qcbs(bid_inputs, technical_scores)
        result_dict = {**stage2.model_dump(), "evaluation_method": "QCBS"}
        logger.info(
            "run_stage2_evaluation(rfp_id=%r) done (QCBS): %d ranked, winner=%s",
            rfp_id, len(stage2.ranking), stage2.winner,
        )
    else:
        stage2 = score_stage2(
            bid_inputs,
            price_band_percent=structured_rfp.price_band_percent,
            mse_share_percent=structured_rfp.mse_share_percent,
        )
        result_dict = {**stage2.model_dump(), "evaluation_method": "L1"}
        logger.info(
            "run_stage2_evaluation(rfp_id=%r) done (L1): %d ranked, tied_for_l1=%s",
            rfp_id, len(stage2.ranking), stage2.tied_for_l1,
        )

    save_stage2_result(pool, rfp_id, result_dict)
