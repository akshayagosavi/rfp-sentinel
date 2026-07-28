"""
Milestone 2 of the rule-based scoring redesign -- score_value() against
hand-written Rule JSON fixtures (tests/data/rules/), zero Ollama. Isolates
"is the engine correct" from "did extraction work" before milestone 4+
introduces the LLM.
"""
import json
from pathlib import Path

from pydantic import TypeAdapter

from backend.models.rule import Rule
from backend.scoring.criterion_evaluator import score_value

_FIXTURE_DIR = Path(__file__).parent / "data" / "rules"
_RULE_ADAPTER = TypeAdapter(Rule)


def _load(name: str) -> Rule:
    return _RULE_ADAPTER.validate_python(json.loads((_FIXTURE_DIR / name).read_text()))


# --- range ---


def test_range_top_tier():
    rule = _load("experience_range.json")
    result = score_value(rule, 12)
    assert result.score == 20
    assert result.max_score == 20
    assert result.matched.kind == "tier"
    assert result.matched.detail["tier_index"] == 0


def test_range_mid_tier_is_not_partial_credit():
    # A value in the 5-9 tier fully satisfies that band -- it's a real,
    # complete match, not a partial one. This is the exact distinction the
    # design review caught: scoring and compliance are independent concepts.
    rule = _load("experience_range.json")
    result = score_value(rule, 7)
    assert result.score == 12
    assert result.matched.kind == "tier"
    assert result.matched.detail["tier_index"] == 1


def test_range_lowest_tier_is_zero_but_still_matched():
    rule = _load("experience_range.json")
    result = score_value(rule, 2)
    assert result.score == 0
    assert result.matched.kind == "tier"  # matched a real tier, just one worth 0 marks
    assert result.matched.detail["tier_index"] == 2


def test_range_boundary_values_inclusive():
    rule = _load("experience_range.json")
    assert score_value(rule, 10).matched.detail["tier_index"] == 0  # exactly the unbounded tier's floor
    assert score_value(rule, 9).matched.detail["tier_index"] == 1   # exactly the mid tier's ceiling
    assert score_value(rule, 5).matched.detail["tier_index"] == 1   # exactly the mid tier's floor


def test_range_no_value_found():
    rule = _load("experience_range.json")
    result = score_value(rule, None)
    assert result.score == 0
    assert result.max_score == 20
    assert result.matched.kind == "not_found"


def test_range_unparseable_value():
    rule = _load("experience_range.json")
    result = score_value(rule, "not a number")
    assert result.score == 0
    assert result.matched.kind == "not_found"


# --- lookup ---


def test_lookup_top_entry():
    rule = _load("gpu_lookup.json")
    result = score_value(rule, "H100")
    assert result.score == 25
    assert result.max_score == 25
    assert result.matched.kind == "table_entry"
    assert result.matched.detail["key"] == "h100"


def test_lookup_case_and_punctuation_insensitive():
    rule = _load("gpu_lookup.json")
    result = score_value(rule, " A-100 ")
    assert result.score == 18


def test_lookup_unmatched_value_uses_default():
    rule = _load("gpu_lookup.json")
    result = score_value(rule, "RTX 4090")
    assert result.score == 0
    assert result.matched.kind == "default"


def test_lookup_no_value_found():
    rule = _load("gpu_lookup.json")
    result = score_value(rule, None)
    assert result.score == 0
    assert result.matched.kind == "not_found"


def test_lookup_boolean_style():
    rule = _load("iso_boolean_lookup.json")
    assert score_value(rule, "true").score == 10
    assert score_value(rule, "false").score == 0
    assert score_value(rule, "True").score == 10  # case-insensitive, same normalization as GPU matching
