"""
Generalized scoring rules -- what a criterion's marks/points breakdown looks
like when the RFP states one explicitly (e.g. "10+ years = 20 marks, 5-9
years = 12 marks" or "H100 = 25 marks, A100 = 18 marks"), instead of every
scored criterion being worth an equal, arbitrary 1/N share regardless of what
the RFP itself says it's worth (see backend/scoring/scoring.py's VERDICT_SCORE
average, which this is designed to sit alongside, not replace outright --
a criterion with no rule keeps scoring exactly as it does today).

Only two shapes for now: range (numeric thresholds/tiers, including
percentage-based ones) and lookup (a discrete table, e.g. model name -> marks,
or a boolean condition expressed as a two-entry table). A third "formula"
type (e.g. "revenue ratio -> marks") was considered and deliberately dropped:
a formula like that typically needs a reference value from OUTSIDE the single
bid being scored (the highest bidder's revenue, a cross-bid comparison), which
this schema and its evaluator (criterion_evaluator.py) have no mechanism for
-- they only ever see one bid's own extracted value. Revisit only once a real
RFP is found whose formula is genuinely self-contained per-bid.

A single flat `field` per rule is also a known, deliberate limitation -- a
real RFP could tier a value along two dimensions at once (e.g. "government
sector experience: 20 marks, private sector: 10 marks"). Not solved here;
LookupRule's string keys can absorb small discrete cases via a compound key
(e.g. "government_10plus") if one is actually encountered, without a schema
change. A generic condition/DSL redesign was considered and deferred for the
same reason formula was: no real RFP has shown a shape that range/lookup
can't already express.
"""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class RangeTier(BaseModel):
    min_value: float | None = None  # None = unbounded below
    max_value: float | None = None  # None = unbounded above
    score: float


class RangeRule(BaseModel):
    type: Literal["range"] = "range"
    field: str  # name of the value this rule scores, e.g. "years_of_experience", "uptime_percent"
    tiers: list[RangeTier]


class LookupRule(BaseModel):
    type: Literal["lookup"] = "lookup"
    field: str  # e.g. "gpu_model", or a boolean condition's name e.g. "has_iso_27001"
    table: dict[str, float]  # normalized key -> score, e.g. {"h100": 25, "a100": 18} or {"true": 10, "false": 0}
    default_score: float = 0.0  # score when the extracted value matches nothing in the table


Rule = Annotated[Union[RangeRule, LookupRule], Field(discriminator="type")]


def rule_max_score(rule: Rule) -> float:
    """The rule's own ceiling -- never stored as a separate field so the LLM
    extracting a rule can't state a max_score inconsistent with its own
    tiers/table. Used both by criterion_evaluator.score_value() and by
    anything that needs to know a rule's weight without evaluating a value."""
    if rule.type == "range":
        return max((t.score for t in rule.tiers), default=0.0)
    return max([*rule.table.values(), rule.default_score], default=0.0)
