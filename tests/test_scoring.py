"""
M12 tests -- pure functions, real Criterion/EvidenceItem objects, no
mocking needed. The MSE price-match cases mirror the exact worked example
validated earlier in the project (a non-MSE L1 at ~8L vs. an MSE bidder at
~9L activates the preference; the same L1 vs. an MSE bidder at 10L does
not, since 10L exceeds L1's 15% band ceiling of 9.2L).
"""
from backend.models.evidence import EvidenceItem
from backend.models.rfp import Criterion
from backend.scoring.scoring import BidInput, apply_mse_price_match, score_stage1, score_stage2


def _criterion(id_, mandatory, category="technical"):
    return Criterion(id=id_, text=f"criterion {id_}", mandatory=mandatory, category=category, page_number=1)


def _evidence(criterion_id, verdict, bid_id="bid-1"):
    return EvidenceItem(criterion_id=criterion_id, bid_id=bid_id, verdict=verdict)


# --- Stage 1: technical gate ---


def test_stage1_fails_on_mandatory_fail():
    criteria = [_criterion("c1", mandatory=True), _criterion("c2", mandatory=True)]
    evidence = [_evidence("c1", "pass"), _evidence("c2", "fail")]
    result = score_stage1(criteria, evidence)
    assert result.passed is False
    assert result.failed_criteria == ["c2"]
    assert result.blocked_pending_review is False


def test_stage1_blocked_pending_review_on_mandatory_not_found():
    criteria = [_criterion("c1", mandatory=True), _criterion("c2", mandatory=True)]
    evidence = [_evidence("c1", "pass"), _evidence("c2", "not_found")]
    result = score_stage1(criteria, evidence)
    assert result.passed is True  # not_found never auto-fails
    assert result.blocked_pending_review is True
    assert result.pending_criteria == ["c2"]


def test_stage1_passes_clean():
    criteria = [_criterion("c1", mandatory=True), _criterion("c2", mandatory=False)]
    evidence = [_evidence("c1", "pass"), _evidence("c2", "partial")]
    result = score_stage1(criteria, evidence)
    assert result.passed is True
    assert result.blocked_pending_review is False
    assert result.failed_criteria == []
    assert result.pending_criteria == []


def test_stage1_optional_criterion_never_gates():
    # An optional criterion failing shouldn't disqualify the bidder.
    criteria = [_criterion("c1", mandatory=True), _criterion("c2", mandatory=False)]
    evidence = [_evidence("c1", "pass"), _evidence("c2", "fail")]
    result = score_stage1(criteria, evidence)
    assert result.passed is True
    assert result.failed_criteria == []


def test_stage1_technical_score_excludes_eligibility():
    criteria = [
        _criterion("c1", mandatory=True, category="eligibility"),  # gate-only, excluded from score
        _criterion("c2", mandatory=True, category="technical"),
        _criterion("c3", mandatory=False, category="financial"),
    ]
    evidence = [_evidence("c1", "pass"), _evidence("c2", "pass"), _evidence("c3", "fail")]
    result = score_stage1(criteria, evidence)
    # Only c2 (pass=1.0) and c3 (fail=0.0) count -> average 0.5 -> 50.0
    assert result.technical_score == 50.0


def test_stage1_technical_score_zero_when_nothing_scored():
    criteria = [_criterion("c1", mandatory=True, category="eligibility")]
    evidence = [_evidence("c1", "pass")]
    result = score_stage1(criteria, evidence)
    assert result.technical_score == 0.0


# --- Stage 2: MII filter, price ranking, ties ---


def test_stage2_mii_filter_excludes_non_local():
    bids = [
        BidInput(bid_id="local", price=100, is_mii_local=True, is_mse=False),
        BidInput(bid_id="foreign", price=50, is_mii_local=False, is_mse=False),
    ]
    result = score_stage2(bids)
    assert [b["bid_id"] for b in result.ranking] == ["local"]  # cheaper non-local bidder excluded entirely


def test_stage2_ranks_by_price_ascending():
    bids = [
        BidInput(bid_id="b1", price=300, is_mii_local=True, is_mse=False),
        BidInput(bid_id="b2", price=100, is_mii_local=True, is_mse=False),
        BidInput(bid_id="b3", price=200, is_mii_local=True, is_mse=False),
    ]
    result = score_stage2(bids)
    assert [b["bid_id"] for b in result.ranking] == ["b2", "b3", "b1"]


def test_stage2_detects_price_tie():
    bids = [
        BidInput(bid_id="b1", price=100, is_mii_local=True, is_mse=False),
        BidInput(bid_id="b2", price=100, is_mii_local=True, is_mse=False),
        BidInput(bid_id="b3", price=150, is_mii_local=True, is_mse=False),
    ]
    result = score_stage2(bids)
    assert set(result.tied_for_l1) == {"b1", "b2"}


def test_stage2_no_tie_when_unique_lowest():
    bids = [
        BidInput(bid_id="b1", price=100, is_mii_local=True, is_mse=False),
        BidInput(bid_id="b2", price=150, is_mii_local=True, is_mse=False),
    ]
    result = score_stage2(bids)
    assert result.tied_for_l1 == []


def test_stage2_mse_price_match_skipped_without_params():
    bids = [BidInput(bid_id="b1", price=100, is_mii_local=True, is_mse=False)]
    result = score_stage2(bids)  # no price_band_percent / mse_share_percent passed
    assert result.mse_price_match is None


# --- MSE price-match: the validated 8L-vs-9L (activates) / 8L-vs-10L (doesn't) example ---


def test_mse_price_match_activates_within_15_percent_band():
    # L1 (non-MSE) at 8,00,000; MSE bidder at 9,00,000 -- within 8L * 1.15 = 9.2L
    ranked = [("l1-bidder", 800_000, False), ("mse-bidder", 900_000, True)]
    result = apply_mse_price_match(ranked, l1_bid_ids=["l1-bidder"], price_band_percent=15, mse_share_percent=60)
    assert result.activated is True
    assert result.matching_mse_bid_id == "mse-bidder"
    assert result.mse_share_percent == 60
    assert result.l1_share_percent == 40


def test_mse_price_match_does_not_activate_outside_15_percent_band():
    # Same L1 at 8,00,000; MSE bidder at 10,00,000 -- exceeds the 9.2L ceiling.
    # This is the exact scenario confirmed earlier: MSME does NOT automatically win.
    ranked = [("l1-bidder", 800_000, False), ("mse-bidder", 1_000_000, True)]
    result = apply_mse_price_match(ranked, l1_bid_ids=["l1-bidder"], price_band_percent=15, mse_share_percent=60)
    assert result.activated is False
    assert result.l1_share_percent == 100.0
    assert result.matching_mse_bid_id is None


def test_mse_price_match_l1_already_mse_skips_preference():
    ranked = [("l1-bidder", 800_000, True)]
    result = apply_mse_price_match(ranked, l1_bid_ids=["l1-bidder"], price_band_percent=15, mse_share_percent=60)
    assert result.activated is False
    assert result.l1_share_percent == 100.0


def test_mse_price_match_no_mse_bidder_present():
    ranked = [("l1-bidder", 800_000, False), ("other-bidder", 850_000, False)]
    result = apply_mse_price_match(ranked, l1_bid_ids=["l1-bidder"], price_band_percent=15, mse_share_percent=60)
    assert result.activated is False


def test_mse_price_match_tied_l1_uses_shared_price():
    # Two bidders tie for L1 -- band math should still work off the shared price.
    ranked = [("b1", 800_000, False), ("b2", 800_000, False), ("mse-bidder", 900_000, True)]
    result = apply_mse_price_match(ranked, l1_bid_ids=["b1", "b2"], price_band_percent=15, mse_share_percent=60)
    assert result.activated is True
    assert result.l1_price == 800_000
