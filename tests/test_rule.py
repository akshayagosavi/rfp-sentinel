"""
Milestone 1 of the rule-based scoring redesign -- the Rule schema itself and
Criterion's new (backward-compatible, default-None) `rule` field. Pure
Pydantic, no LLM/Qdrant.
"""
from backend.models.rfp import Criterion
from backend.models.rule import LookupRule, RangeRule, RangeTier, Rule, rule_max_score


def test_criterion_rule_defaults_to_none():
    # A Criterion built exactly like every one in tests/test_scoring.py today
    # (no rule= argument at all) must still work unchanged.
    c = Criterion(id="c1", text="some criterion", mandatory=False, category="technical", page_number=1)
    assert c.rule is None


def test_range_rule_round_trip():
    rule = RangeRule(
        field="years_of_experience",
        tiers=[
            RangeTier(min_value=10, max_value=None, score=20),
            RangeTier(min_value=5, max_value=9, score=12),
            RangeTier(min_value=0, max_value=4, score=0),
        ],
    )
    c = Criterion(id="c1", text="min 5 years experience", mandatory=False, category="technical", page_number=1, rule=rule)
    dumped = c.model_dump()
    restored = Criterion.model_validate(dumped)
    assert restored.rule.type == "range"
    assert restored.rule.field == "years_of_experience"
    assert len(restored.rule.tiers) == 3


def test_lookup_rule_round_trip():
    rule = LookupRule(field="gpu_model", table={"h100": 25, "a100": 18}, default_score=0)
    c = Criterion(id="c1", text="GPU model offered", mandatory=False, category="technical", page_number=1, rule=rule)
    restored = Criterion.model_validate(c.model_dump())
    assert restored.rule.type == "lookup"
    assert restored.rule.table["h100"] == 25


def test_rule_max_score_derived_from_range_tiers():
    rule = RangeRule(field="x", tiers=[RangeTier(min_value=0, max_value=4, score=0), RangeTier(min_value=5, max_value=None, score=20)])
    assert rule_max_score(rule) == 20


def test_rule_max_score_derived_from_lookup_table():
    rule = LookupRule(field="gpu_model", table={"h100": 25, "a100": 18}, default_score=0)
    assert rule_max_score(rule) == 25


def test_rule_max_score_boolean_style_lookup():
    # A binary condition ("has ISO 27001 cert: +10 marks") expressed as a
    # two-entry lookup table, per the design's fold-boolean-into-lookup choice.
    rule = LookupRule(field="has_iso_27001", table={"true": 10, "false": 0})
    assert rule_max_score(rule) == 10


def test_discriminated_union_rejects_unknown_type():
    import pytest
    from pydantic import TypeAdapter, ValidationError

    adapter = TypeAdapter(Rule)
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "formula", "expression": "x + 1"})
