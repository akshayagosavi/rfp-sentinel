"""
M12: deterministic scoring engine -- turns per-criterion EvidenceItem
verdicts into a pass/fail gate (Stage 1) and a ranked shortlist (Stage 2).
Pure Python, zero LLM/Qdrant dependency by design -- the one part of this
system meant to be fully unit-tested with fixtures (see
tests/test_scoring.py), not exercised against a live model.

Stage 1 (technical gate), per bidder: any mandatory criterion with verdict
'fail' OR 'partial' -> the bidder is out. Mandatory criteria are a binary
gate, not a scored one -- GeM's own technical evaluation gives no partial
credit at this stage (a mismatch on a "must/shall" requirement is fatal,
even a single one), so 'partial' compliance with a mandatory requirement
is still non-compliance, same as an outright 'fail'. This is different
from a non-mandatory ("preferred") criterion, where 'partial' earns half
credit in technical_score below rather than disqualifying anyone -- the
gate is binary, the score is graded, and mandatory/category is what
decides which regime a given criterion falls under. Mandatory 'not_found'
-> held for human review, never auto-failed -- same "don't guess, ask a
human" discipline used everywhere else evidence is uncertain (Checkpoint
A's override flow, the document-completeness checklist): unlike 'partial'
(the model found real, relevant content that still falls short), an
absence of any matching content could be a genuine failure or could be a
retrieval miss, so it isn't given the same automatic-fail treatment.
A technical_score is also computed, but only from technical/financial/
other criteria -- eligibility criteria are treated as gate-only
(mandatory/binary), not part of the weighted score, per the plan's
scoring design.

Stage 2 (rank), for Stage-1 survivors only, branches on the RFP's own
evaluation_method (now extracted from its "Evaluation Method" field, see
extract_rfp_criteria.py -- defaults to L1 if absent/ambiguous, since L1 is
the only value seen in real documents so far):
  - L1: MII filter -> price rank -> MSE price-match. score_stage2() below.
  - QCBS (price + technical quality blended): MII filter -> blend each
    Stage-1-passed bid's technical_score with a price_score into one
    final_score, ranked descending. score_stage2_qcbs() below. Built once
    a real RFP's evaluation_method extraction made the branch meaningful
    to reach; no real QCBS RFP has been seen yet to validate the default
    70/30 technical/price weighting against, so treat that default as a
    placeholder until a real one is found, not a confirmed GeM constant.

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
both are required parameters here, not assumed constants. Now sourced
from extract_rfp_criteria.py's _extract_mse_preference_params() (verified
against a second real RFP: 15% band, 25% share), falling back to None
(no price-match computed) when an RFP doesn't state its own numbers --
this module only does the arithmetic once the numbers are known, it never
guesses them.
"""
import random

from pydantic import BaseModel

from backend.models.evidence import EvidenceItem
from backend.models.rfp import Criterion

VERDICT_SCORE = {"pass": 1.0, "partial": 0.5, "fail": 0.0, "not_found": 0.0}

# Eligibility criteria gate Stage 1 (mandatory/binary) but aren't part of
# the weighted technical_score -- only these categories contribute to it.
SCORED_CATEGORIES = {"technical", "financial", "other"}


class Stage1Result(BaseModel):
    bid_id: str
    passed: bool
    blocked_pending_review: bool  # passed, but a mandatory criterion is still awaiting human review
    technical_score: float  # 0-100, over technical/financial/other criteria only
    failed_criteria: list[str] = []  # criterion_ids that failed (verdict fail or partial) a mandatory check
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
        if verdict in ("fail", "partial"):
            failed_criteria.append(c.id)
        elif verdict == "not_found":
            pending_criteria.append(c.id)

    passed = len(failed_criteria) == 0
    blocked_pending_review = passed and len(pending_criteria) > 0

    # Weighted per-criterion contribution: a criterion with a rule_result
    # (see backend/models/rule.py, backend/scoring/criterion_evaluator.py)
    # contributes its own real score/max_score, honoring whatever marks the
    # RFP itself assigned it; a criterion with no rule falls back to today's
    # implicit equal weight of 1.0 via VERDICT_SCORE, exactly as before rules
    # existed. When zero criteria have a rule this is algebraically
    # identical to the old plain average (max_sum == len(scored_criteria)).
    scored_criteria = [c for c in criteria if c.category in SCORED_CATEGORIES]
    raw_sum = max_sum = 0.0
    for c in scored_criteria:
        e = evidence_by_criterion.get(c.id)
        if e is not None and e.rule_result is not None:
            raw_sum += e.rule_result["score"]
            max_sum += e.rule_result["max_score"]
        else:
            verdict = e.verdict if e is not None else "not_found"
            raw_sum += VERDICT_SCORE[verdict] * 1.0
            max_sum += 1.0
    technical_score = (raw_sum / max_sum * 100) if max_sum > 0 else 0.0

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
    mii_restricted: bool = True,
) -> Stage2Result:
    """MII filter runs first (excludes non-local suppliers before anything
    else) UNLESS mii_restricted is False -- that flag is this RFP's own
    mii_restricted field (StructuredRFP), true unless this specific RFP's
    ATC text is confirmed not to require Class-I/II-local-only bidding.
    Defaults to True here too so any existing caller that doesn't pass it
    keeps today's behavior unchanged. Then price ranking, then the MSE
    price-match. L1 only -- see module docstring for why QCBS isn't
    included in this build.

    If L1 is a tie, mse_price_match is only computed automatically when
    every tied bidder shares the same MSE status (the answer is
    unambiguous either way in that case); a genuinely mixed tie (some
    tied bidders MSE, some not) leaves mse_price_match unset until the
    buyer resolves the tie via run_l1_selection() -- MSE price-matching
    can't be determined without knowing which single bidder is actually L1."""
    mii_filtered = [b for b in bids if b.is_mii_local] if mii_restricted else list(bids)
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


# Placeholder default -- no real QCBS RFP has been seen yet to confirm
# GeM's typical split against; see module docstring. Always overridable by
# a caller that has the RFP's own stated weights.
_DEFAULT_QCBS_TECHNICAL_WEIGHT = 0.7
_DEFAULT_QCBS_PRICE_WEIGHT = 0.3


class QcbsResult(BaseModel):
    ranking: list[dict]  # [{bid_id, price, technical_score, price_score, final_score}], final_score descending
    winner: str | None = None
    technical_weight: float = _DEFAULT_QCBS_TECHNICAL_WEIGHT
    price_weight: float = _DEFAULT_QCBS_PRICE_WEIGHT


def score_stage2_qcbs(
    bids: list[BidInput],
    technical_scores: dict[str, float],
    technical_weight: float = _DEFAULT_QCBS_TECHNICAL_WEIGHT,
    price_weight: float = _DEFAULT_QCBS_PRICE_WEIGHT,
    mii_restricted: bool = True,
) -> QcbsResult:
    """QCBS: unlike L1, a bid's technical_score (from score_stage1) keeps
    mattering after the Stage 1 gate -- it's blended with a price_score
    (cheapest of the Stage-1-qualified, MII-local bidders scores 100,
    others proportionally less) into one final_score, ranked descending.
    technical_scores maps bid_id -> the technical_score already computed
    by score_stage1 -- this function doesn't recompute it, just consumes
    it, same "one calculation, two consumers" relationship described in
    this module's docstring.

    mii_restricted mirrors score_stage2()'s parameter of the same name --
    True (default, unchanged existing behavior) excludes non-local bidders
    entirely; False includes everyone, ranked purely on technical/price."""
    mii_filtered = [b for b in bids if b.is_mii_local] if mii_restricted else list(bids)
    if not mii_filtered:
        return QcbsResult(ranking=[], technical_weight=technical_weight, price_weight=price_weight)

    lowest_price = min(b.price for b in mii_filtered)
    ranking = []
    for b in mii_filtered:
        price_score = (lowest_price / b.price) * 100
        tech_score = technical_scores.get(b.bid_id, 0.0)
        final_score = technical_weight * tech_score + price_weight * price_score
        ranking.append({
            "bid_id": b.bid_id, "price": b.price, "technical_score": tech_score,
            "price_score": round(price_score, 2), "final_score": round(final_score, 2),
        })
    ranking.sort(key=lambda r: -r["final_score"])

    return QcbsResult(
        ranking=ranking, winner=ranking[0]["bid_id"],
        technical_weight=technical_weight, price_weight=price_weight,
    )
