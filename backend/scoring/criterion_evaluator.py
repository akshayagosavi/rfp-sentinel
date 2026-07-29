"""
Milestone 2 of the rule-based scoring redesign: score_value() turns a raw
value extracted from a bidder's evidence into a graded score, per this
criterion's own Rule (backend/models/rule.py). Pure Python, zero LLM/Qdrant
imports -- same discipline as backend/scoring/scoring.py, and same *style*:
a plain function, not a class. This codebase has no "Engine" class pattern
anywhere (score_stage1/score_stage2/apply_mse_price_match/run_l1_selection
are all plain functions), and two dispatch branches don't need one.

Deliberately takes a plain extracted value, never an EvidenceItem, citation,
or verdict -- its only job is value -> score. Compliance (the mandatory gate)
is a completely separate concern, always answered by the existing
classify()-based flow in retrieve_and_extract_evidence.py, regardless of
whether a criterion also has a rule here. Conflating the two -- e.g. deriving
a pass/fail/partial verdict from where a value lands in a tier table -- was
tried and rejected during design: a bidder landing in a lower-marks tier has
still fully satisfied that tier, not "partially complied." No verdict/pass/
fail/partial concept exists anywhere in this module.
"""
import re

from pydantic import BaseModel

from backend.models.rule import LookupRule, RangeRule, Rule, rule_max_score


class RuleMatch(BaseModel):
    # Structured, not free text -- a human-readable string can always be
    # rendered from this later (a frontend/report concern); going the other
    # direction can't.
    kind: str  # "tier" | "table_entry" | "default" | "not_found"
    detail: dict = {}


class RuleResult(BaseModel):
    score: float
    max_score: float
    matched: RuleMatch


def _normalize(text) -> str:
    # Same normalization idea as extract_rfp_criteria.py's
    # _normalize_for_matching() (lowercase, strip non-alphanumeric) -- not
    # imported from there, since scoring/ stays dependency-free of graph/
    # (mirroring scoring.py's own "zero imports from llm/" discipline).
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def _score_range(rule: RangeRule, value: float | str | None) -> RuleResult:
    max_score = rule_max_score(rule)
    if value is None:
        return RuleResult(score=0.0, max_score=max_score, matched=RuleMatch(kind="not_found"))

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return RuleResult(
            score=0.0, max_score=max_score, matched=RuleMatch(kind="not_found", detail={"value": value})
        )

    for i, tier in enumerate(rule.tiers):
        lower_ok = tier.min_value is None or numeric_value >= tier.min_value
        upper_ok = tier.max_value is None or numeric_value <= tier.max_value
        if lower_ok and upper_ok:
            return RuleResult(
                score=tier.score, max_score=max_score,
                matched=RuleMatch(
                    kind="tier",
                    detail={"tier_index": i, "min": tier.min_value, "max": tier.max_value, "value": numeric_value},
                ),
            )

    # A parseable value that doesn't fall into any defined tier (a gap in the
    # RFP's own table, or a value below/above every tier) -- no score is
    # defined for it, same as "no value found."
    return RuleResult(
        score=0.0, max_score=max_score, matched=RuleMatch(kind="not_found", detail={"value": numeric_value})
    )


def _score_lookup(rule: LookupRule, value: float | str | None) -> RuleResult:
    max_score = rule_max_score(rule)
    if value is None:
        return RuleResult(score=0.0, max_score=max_score, matched=RuleMatch(kind="not_found"))

    normalized_value = _normalize(value)
    normalized_table = {_normalize(key): (key, score) for key, score in rule.table.items()}
    if normalized_value in normalized_table:
        original_key, score = normalized_table[normalized_value]
        return RuleResult(score=score, max_score=max_score, matched=RuleMatch(kind="table_entry", detail={"key": original_key}))

    return RuleResult(
        score=rule.default_score, max_score=max_score, matched=RuleMatch(kind="default", detail={"value": value})
    )


def score_value(rule: Rule, value: float | str | None) -> RuleResult:
    """One dispatch point on rule.type. `value` is None when nothing could be
    extracted from the bid. Never raises -- an unparseable/unmatched value
    degrades to a zero score with a "not_found"/"default" match, same "don't
    guess, surface it" discipline used everywhere else in this project."""
    if rule.type == "range":
        return _score_range(rule, value)
    return _score_lookup(rule, value)
