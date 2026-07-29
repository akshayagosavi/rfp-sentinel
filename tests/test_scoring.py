"""
M12 tests -- pure functions, real Criterion/EvidenceItem objects, no
mocking needed. The MSE price-match cases mirror the exact worked example
validated earlier in the project (a non-MSE L1 at ~8L vs. an MSE bidder at
~9L activates the preference; the same L1 vs. an MSE bidder at 10L does
not, since 10L exceeds L1's 15% band ceiling of 9.2L).
"""
from backend.models.evidence import EvidenceItem
from backend.models.rfp import Criterion
from backend.scoring.scoring import (
    BidInput,
    apply_mse_price_match,
    run_l1_selection,
    score_stage1,
    score_stage2,
    score_stage2_qcbs,
)


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


def test_stage1_fails_on_mandatory_partial():
    # GeM's technical gate gives no partial credit on a mandatory ("must/
    # shall") requirement -- a mismatch is fatal even if the bid partially
    # addresses it. This must fail the bidder exactly like an outright
    # 'fail' verdict, not silently pass through ungated.
    criteria = [_criterion("c1", mandatory=True), _criterion("c2", mandatory=True)]
    evidence = [_evidence("c1", "pass"), _evidence("c2", "partial")]
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


# --- Stage 1: rule-based scoring (milestone 3 of the rule-engine redesign) ---


def _rule_evidence(criterion_id, verdict, score, max_score, bid_id="bid-1"):
    return EvidenceItem(
        criterion_id=criterion_id, bid_id=bid_id, verdict=verdict,
        rule_result={"score": score, "max_score": max_score, "matched": {"kind": "tier", "detail": {}}},
    )


def test_stage1_rule_result_used_instead_of_verdict_score():
    # A single rule-scored criterion earning 15/20 marks -> 75%, NOT the
    # crude verdict-average (which would just be 100% for a "pass").
    criteria = [_criterion("c1", mandatory=False, category="technical")]
    evidence = [_rule_evidence("c1", "pass", score=15, max_score=20)]
    result = score_stage1(criteria, evidence)
    assert result.technical_score == 75.0


def test_stage1_blends_rule_scored_and_verdict_scored_criteria():
    # c1 has a real rule (15/20 marks); c2 has no rule and falls back to
    # today's implicit weight-of-1 verdict scoring (fail -> 0/1).
    criteria = [
        _criterion("c1", mandatory=False, category="technical"),
        _criterion("c2", mandatory=False, category="technical"),
    ]
    evidence = [_rule_evidence("c1", "pass", score=15, max_score=20), _evidence("c2", "fail")]
    result = score_stage1(criteria, evidence)
    # raw_sum = 15 + 0 = 15; max_sum = 20 + 1 = 21
    assert result.technical_score == round(15 / 21 * 100, 2)


def test_stage1_mid_tier_rule_score_does_not_affect_mandatory_gate():
    # The exact bug the design review caught: a mandatory criterion that
    # lands in a lower (but real) marks tier has still fully satisfied it --
    # the gate is driven purely by verdict, never by where the rule_result's
    # score falls relative to its own max_score.
    criteria = [_criterion("c1", mandatory=True, category="technical")]
    evidence = [_rule_evidence("c1", "pass", score=12, max_score=20)]  # mid-tier score, but verdict=pass
    result = score_stage1(criteria, evidence)
    assert result.passed is True
    assert result.failed_criteria == []
    assert result.technical_score == 60.0  # 12/20 * 100 -- scoring and gating are independent numbers


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


def test_stage2_mii_restricted_false_includes_non_local():
    # An RFP that doesn't restrict to Class-I/II local suppliers only --
    # a non-local bidder should be ranked normally, not silently dropped.
    bids = [
        BidInput(bid_id="local", price=100, is_mii_local=True, is_mse=False),
        BidInput(bid_id="foreign", price=50, is_mii_local=False, is_mse=False),
    ]
    result = score_stage2(bids, mii_restricted=False)
    assert [b["bid_id"] for b in result.ranking] == ["foreign", "local"]


def test_stage2_mse_price_match_skipped_without_params():
    bids = [BidInput(bid_id="b1", price=100, is_mii_local=True, is_mse=False)]
    result = score_stage2(bids)  # no price_band_percent / mse_share_percent passed
    assert result.mse_price_match is None


# --- MSE price-match: the validated 8L-vs-9L (activates) / 8L-vs-10L (doesn't) example ---


def test_mse_price_match_activates_within_15_percent_band():
    # L1 (non-MSE) at 8,00,000; MSE bidder at 9,00,000 -- within 8L * 1.15 = 9.2L
    ranked = [("l1-bidder", 800_000, False), ("mse-bidder", 900_000, True)]
    result = apply_mse_price_match(ranked, l1_bid_id="l1-bidder", price_band_percent=15, mse_share_percent=60)
    assert result.activated is True
    assert result.matching_mse_bid_id == "mse-bidder"
    assert result.mse_share_percent == 60
    assert result.l1_share_percent == 40


def test_mse_price_match_does_not_activate_outside_15_percent_band():
    # Same L1 at 8,00,000; MSE bidder at 10,00,000 -- exceeds the 9.2L ceiling.
    # This is the exact scenario confirmed earlier: MSME does NOT automatically win.
    ranked = [("l1-bidder", 800_000, False), ("mse-bidder", 1_000_000, True)]
    result = apply_mse_price_match(ranked, l1_bid_id="l1-bidder", price_band_percent=15, mse_share_percent=60)
    assert result.activated is False
    assert result.l1_share_percent == 100.0
    assert result.matching_mse_bid_id is None


def test_mse_price_match_l1_already_mse_skips_preference():
    ranked = [("l1-bidder", 800_000, True)]
    result = apply_mse_price_match(ranked, l1_bid_id="l1-bidder", price_band_percent=15, mse_share_percent=60)
    assert result.activated is False
    assert result.l1_share_percent == 100.0


def test_mse_price_match_no_mse_bidder_present():
    ranked = [("l1-bidder", 800_000, False), ("other-bidder", 850_000, False)]
    result = apply_mse_price_match(ranked, l1_bid_id="l1-bidder", price_band_percent=15, mse_share_percent=60)
    assert result.activated is False


# --- Tied L1 with mixed MSE status: the bug found and fixed this round ---


def test_stage2_mixed_mse_tie_defers_price_match_to_buyer():
    # b1 (non-MSE) and b2 (MSE) tie for L1 -- genuinely ambiguous who "L1" is
    # for price-match purposes, so this must NOT auto-resolve.
    bids = [
        BidInput(bid_id="b1", price=800_000, is_mii_local=True, is_mse=False),
        BidInput(bid_id="b2", price=800_000, is_mii_local=True, is_mse=True),
    ]
    result = score_stage2(bids, price_band_percent=15, mse_share_percent=60)
    assert set(result.tied_for_l1) == {"b1", "b2"}
    assert result.mse_price_match is None  # ambiguous -- must wait for run_l1_selection()


def test_stage2_unambiguous_tie_still_computes_price_match():
    # Both tied bidders are non-MSE -- no ambiguity about MSE status even
    # though the tie itself (who wins) is still unresolved.
    bids = [
        BidInput(bid_id="b1", price=800_000, is_mii_local=True, is_mse=False),
        BidInput(bid_id="b2", price=800_000, is_mii_local=True, is_mse=False),
        BidInput(bid_id="mse-bidder", price=900_000, is_mii_local=True, is_mse=True),
    ]
    result = score_stage2(bids, price_band_percent=15, mse_share_percent=60)
    assert set(result.tied_for_l1) == {"b1", "b2"}
    assert result.mse_price_match is not None
    assert result.mse_price_match.activated is True
    assert result.mse_price_match.l1_bid_id in {"b1", "b2"}


# --- run_l1_selection(): GeM's own documented tie-break mechanism ---


def test_run_l1_selection_picks_among_tied_bidders():
    bids = [
        BidInput(bid_id="b1", price=100, is_mii_local=True, is_mse=False),
        BidInput(bid_id="b2", price=100, is_mii_local=True, is_mse=False),
    ]
    winner = run_l1_selection(["b1", "b2"], bids, mse_preference_active=False)
    assert winner in {"b1", "b2"}


def test_run_l1_selection_restricts_to_mse_when_preference_active():
    bids = [
        BidInput(bid_id="non-mse", price=100, is_mii_local=True, is_mse=False),
        BidInput(bid_id="mse-1", price=100, is_mii_local=True, is_mse=True),
        BidInput(bid_id="mse-2", price=100, is_mii_local=True, is_mse=True),
    ]
    for _ in range(20):  # random draw -- run enough times to catch it ever picking the non-MSE bidder
        winner = run_l1_selection(["non-mse", "mse-1", "mse-2"], bids, mse_preference_active=True)
        assert winner in {"mse-1", "mse-2"}


def test_run_l1_selection_falls_back_to_all_tied_when_none_are_mse():
    bids = [
        BidInput(bid_id="b1", price=100, is_mii_local=True, is_mse=False),
        BidInput(bid_id="b2", price=100, is_mii_local=True, is_mse=False),
    ]
    winner = run_l1_selection(["b1", "b2"], bids, mse_preference_active=True)
    assert winner in {"b1", "b2"}


# --- score_stage2_qcbs(): technical quality keeps mattering after the gate ---


def test_qcbs_cheapest_bidder_does_not_always_win():
    # C is priciest but has by far the best technical_score -- at a
    # technical-heavy weighting, C should beat the cheapest bidder B.
    bids = [
        BidInput(bid_id="A", price=500_000, is_mii_local=True, is_mse=True),
        BidInput(bid_id="B", price=470_000, is_mii_local=True, is_mse=False),
        BidInput(bid_id="C", price=540_000, is_mii_local=True, is_mse=False),
    ]
    technical_scores = {"A": 72, "B": 60, "C": 95}
    result = score_stage2_qcbs(bids, technical_scores, technical_weight=0.8, price_weight=0.2)
    assert result.winner == "C"
    assert result.ranking[0]["bid_id"] == "C"


def test_qcbs_cheapest_price_gets_100_price_score():
    bids = [
        BidInput(bid_id="cheap", price=100, is_mii_local=True, is_mse=False),
        BidInput(bid_id="pricier", price=200, is_mii_local=True, is_mse=False),
    ]
    technical_scores = {"cheap": 50, "pricier": 50}
    result = score_stage2_qcbs(bids, technical_scores)
    by_id = {r["bid_id"]: r for r in result.ranking}
    assert by_id["cheap"]["price_score"] == 100.0
    assert by_id["pricier"]["price_score"] == 50.0


def test_qcbs_excludes_non_mii_bidders():
    bids = [
        BidInput(bid_id="local", price=100, is_mii_local=True, is_mse=False),
        BidInput(bid_id="foreign", price=50, is_mii_local=False, is_mse=False),
    ]
    result = score_stage2_qcbs(bids, {"local": 80, "foreign": 90})
    assert [r["bid_id"] for r in result.ranking] == ["local"]


def test_qcbs_empty_ranking_when_no_mii_local_bidders():
    bids = [BidInput(bid_id="foreign", price=50, is_mii_local=False, is_mse=False)]
    result = score_stage2_qcbs(bids, {"foreign": 90})
    assert result.ranking == []
    assert result.winner is None


def test_qcbs_missing_technical_score_defaults_to_zero():
    bids = [BidInput(bid_id="b1", price=100, is_mii_local=True, is_mse=False)]
    result = score_stage2_qcbs(bids, {})  # no technical_score recorded for b1
    assert result.ranking[0]["technical_score"] == 0.0


def test_qcbs_mii_restricted_false_includes_non_local():
    bids = [
        BidInput(bid_id="local", price=100, is_mii_local=True, is_mse=False),
        BidInput(bid_id="foreign", price=50, is_mii_local=False, is_mse=False),
    ]
    result = score_stage2_qcbs(bids, {"local": 80, "foreign": 90}, mii_restricted=False)
    assert {r["bid_id"] for r in result.ranking} == {"local", "foreign"}
