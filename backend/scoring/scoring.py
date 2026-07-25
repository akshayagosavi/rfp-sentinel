"""
M12: deterministic scoring engine -- turns per-criterion EvidenceItem
verdicts into a pass/fail gate (Stage 1) and a ranked shortlist (Stage 2).
Pure Python, zero LLM/Qdrant dependency by design -- the one part of this
system meant to be fully unit-tested with fixtures (see
tests/test_scoring.py), not exercised against a live model.

Stage 1 (technical gate), per bidder: any mandatory criterion with verdict
'fail' -> the bidder is out. Mandatory 'not_found' -> held for human
review, never auto-failed -- same "don't guess, ask a human" discipline
used everywhere else evidence is uncertain (Checkpoint A's override flow,
the document-completeness checklist). A technical_score is also computed,
but only from technical/financial/other criteria -- eligibility criteria
are treated as gate-only (mandatory/binary), not part of the weighted
score, per the plan's scoring design.

Stage 2 (rank), for Stage-1 survivors only: MII filter -> price rank ->
MSE price-match. L1 (lowest price wins) only -- QCBS (price + technical
quality blended) was deliberately left out of this build: every real RFP
processed so far uses L1, nothing extracts evaluation_method from RFP text
yet, and QCBS's weighting/quality-definition questions were still open
during design, not confidently resolved. Tracked as deferred in
ROADMAP.md, not silently missing.

A price tie for L1 is surfaced, and resolved only via run_l1_selection()
below -- an explicit action, not automatic. This mirrors GeM's own real,
documented "Run L1 selection" feature (a buyer-triggered random draw,
sourced from gem.gov.in's own FAQ, not invented): if MSE purchase
preference is active for the RFP, the draw is restricted to the MSE
bidder(s) within the tied group; otherwise it's drawn from everyone tied.
Earlier in this project's history the tie was left entirely to a human
decision because no documented rule could be found -- that's since been
superseded by finding GeM's actual mechanism, tracked in ROADMAP.md.

The MSE price-band percentage and quantity-split ratio are NOT hardcoded
-- the real NIELIT RFP proved a single RFP can override the general
policy's default (25% band, 25/75 split per the 2012 Policy Order) with
its own bid-specific ATC clause (this RFP: 15% band, 60/40 split) -- so
both are required parameters here, not assumed constants. Pulling those
numbers out of an RFP's raw clause text automatically is a separate,
not-yet-built extraction step; this module only does the arithmetic once
the numbers are known.
"""
import random

from pydantic import BaseModel

from backend.models.evidence import EvidenceItem
from backend.models.rfp import Criterion

VERDICT_SCORE = {"pass": 1.0, "partial": 0.5, "fail": 0.0, "not_found": 0.0}

# Eligibility criteria gate Stage 1 (mandatory/binary) but aren't part of
# the weighted technical_score -- only these categories contribute to it.
_SCORED_CATEGORIES = {"technical", "financial", "other"}


class Stage1Result(BaseModel):
    bid_id: str
    passed: bool
    blocked_pending_review: bool  # passed, but a mandatory criterion is still awaiting human review
    technical_score: float  # 0-100, over technical/financial/other criteria only
    failed_criteria: list[str] = []  # criterion_ids that failed a mandatory check
    pending_criteria: list[str] = []  # criterion_ids that are not_found on a mandatory check


def score_stage1(criteria: list[Criterion], evidence: list[EvidenceItem]) -> Stage1Result:
    evidence_by_criterion = {e.criterion_id: e for e in evidence}
    bid_id = evidence[0].bid_id if evidence else ""

    failed_criteria = []
    pending_criteria = []
    for c in criteria:
        if not c.mandatory:
            continue
        verdict = evidence_by_criterion[c.id].verdict if c.id in evidence_by_criterion else "not_found"
        if verdict == "fail":
            failed_criteria.append(c.id)
        elif verdict == "not_found":
            pending_criteria.append(c.id)

    passed = len(failed_criteria) == 0
    blocked_pending_review = passed and len(pending_criteria) > 0

    scored_criteria = [c for c in criteria if c.category in _SCORED_CATEGORIES]
    weighted_sum = sum(
        VERDICT_SCORE[evidence_by_criterion[c.id].verdict if c.id in evidence_by_criterion else "not_found"]
        for c in scored_criteria
    )
    technical_score = (weighted_sum / len(scored_criteria) * 100) if scored_criteria else 0.0

    return Stage1Result(
        bid_id=bid_id,
        passed=passed,
        blocked_pending_review=blocked_pending_review,
        technical_score=round(technical_score, 2),
        failed_criteria=failed_criteria,
        pending_criteria=pending_criteria,
    )


class MsePriceMatchResult(BaseModel):
    activated: bool
    reasoning: str
    l1_bid_id: str
    l1_price: float
    l1_share_percent: float
    matching_mse_bid_id: str | None = None
    mse_share_percent: float = 0.0


def apply_mse_price_match(
    ranked_bids: list[tuple[str, float, bool]],
    l1_bid_id: str,
    price_band_percent: float,
    mse_share_percent: float,
) -> MsePriceMatchResult:
    """ranked_bids: (bid_id, price, is_mse) tuples, already MII-filtered and
    price-sorted ascending -- the caller's job, not this function's.
    l1_bid_id must be a single, already-resolved bidder -- if L1 was a tie,
    resolve it with run_l1_selection() first (or however the buyer chose
    to break it) before calling this. price_band_percent/mse_share_percent
    must come from the specific RFP's own ATC text (e.g. 15% band + 60%
    share for the real NIELIT RFP)."""
    l1_price = next(price for bid_id, price, _ in ranked_bids if bid_id == l1_bid_id)
    l1_is_mse = next(is_mse for bid_id, _, is_mse in ranked_bids if bid_id == l1_bid_id)

    if l1_is_mse:
        return MsePriceMatchResult(
            activated=False,
            reasoning="The L1 bidder is already MSE -- preference doesn't apply, they win the full quantity.",
            l1_bid_id=l1_bid_id, l1_price=l1_price, l1_share_percent=100.0,
        )

    band_ceiling = l1_price * (1 + price_band_percent / 100)
    for bid_id, price, is_mse in ranked_bids:
        if bid_id == l1_bid_id or not is_mse:
            continue
        if price > band_ceiling:
            return MsePriceMatchResult(
                activated=False,
                reasoning=(
                    f"Nearest MSE bidder {bid_id} quoted {price}, above the {price_band_percent}% "
                    f"band ceiling of {band_ceiling:.2f} over L1's {l1_price} -- preference does not "
                    "activate, L1 wins the full quantity."
                ),
                l1_bid_id=l1_bid_id, l1_price=l1_price, l1_share_percent=100.0,
            )
        return MsePriceMatchResult(
            activated=True,
            reasoning=(
                f"MSE bidder {bid_id} quoted {price}, within the {price_band_percent}% band "
                f"(ceiling {band_ceiling:.2f}) -- offered to match L1's price of {l1_price}."
            ),
            l1_bid_id=l1_bid_id, l1_price=l1_price, l1_share_percent=100 - mse_share_percent,
            matching_mse_bid_id=bid_id, mse_share_percent=mse_share_percent,
        )

    return MsePriceMatchResult(
        activated=False,
        reasoning="No MSE bidder found among the ranked bids -- L1 wins the full quantity.",
        l1_bid_id=l1_bid_id, l1_price=l1_price, l1_share_percent=100.0,
    )


class BidInput(BaseModel):
    bid_id: str
    price: float
    is_mii_local: bool  # Make-in-India / local-supplier status -- not yet auto-derived from bid documents
    is_mse: bool  # Micro/Small Enterprise status -- not yet auto-derived from bid documents


def run_l1_selection(tied_bid_ids: list[str], bids: list[BidInput], mse_preference_active: bool) -> str:
    """Mirrors GeM's own documented 'Run L1 selection' feature exactly
    (sourced from gem.gov.in's FAQ, not invented): a buyer-triggered random
    draw among bidders tied for L1, never automatic -- same "surface it,
    don't silently resolve it" discipline used everywhere else in this
    project, just backed by a real GeM mechanism now instead of a guess.

    If MSE purchase preference is active for this RFP, the draw is
    restricted to the MSE bidder(s) within the tied group; if none of the
    tied bidders are MSE, or preference isn't active, it's drawn from
    everyone tied."""
    bids_by_id = {b.bid_id: b for b in bids}
    candidates = tied_bid_ids
    if mse_preference_active:
        mse_candidates = [bid_id for bid_id in tied_bid_ids if bids_by_id[bid_id].is_mse]
        if mse_candidates:
            candidates = mse_candidates
    return random.choice(candidates)


class Stage2Result(BaseModel):
    ranking: list[dict]  # [{bid_id, price}, ...] price-ascending, MII-filtered
    tied_for_l1: list[str] = []  # bid_ids sharing the lowest price -- resolve with run_l1_selection()
    mse_price_match: MsePriceMatchResult | None = None


def score_stage2(
    bids: list[BidInput],
    price_band_percent: float | None = None,
    mse_share_percent: float | None = None,
) -> Stage2Result:
    """MII filter always runs first (excludes non-local suppliers before
    anything else), then price ranking, then the MSE price-match. L1
    only -- see module docstring for why QCBS isn't included in this build.

    If L1 is a tie, mse_price_match is only computed automatically when
    every tied bidder shares the same MSE status (the answer is
    unambiguous either way in that case); a genuinely mixed tie (some
    tied bidders MSE, some not) leaves mse_price_match unset until the
    buyer resolves the tie via run_l1_selection() -- MSE price-matching
    can't be determined without knowing which single bidder is actually L1."""
    mii_filtered = [b for b in bids if b.is_mii_local]
    ranked = sorted(mii_filtered, key=lambda b: b.price)

    result = Stage2Result(ranking=[{"bid_id": b.bid_id, "price": b.price} for b in ranked])

    if not ranked:
        return result

    lowest_price = ranked[0].price
    tied_for_l1 = [b for b in ranked if b.price == lowest_price]
    if len(tied_for_l1) > 1:
        result.tied_for_l1 = [b.bid_id for b in tied_for_l1]

    mse_statuses = {b.is_mse for b in tied_for_l1}
    l1_unambiguous = len(mse_statuses) == 1  # every tied L1 bidder shares the same MSE status

    if price_band_percent is not None and mse_share_percent is not None and l1_unambiguous:
        tuples = [(b.bid_id, b.price, b.is_mse) for b in ranked]
        result.mse_price_match = apply_mse_price_match(
            tuples, tied_for_l1[0].bid_id, price_band_percent, mse_share_percent
        )

    return result
