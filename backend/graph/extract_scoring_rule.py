"""
Milestone 5 of the rule-based scoring redesign: infer_rule() converts a
criterion's own scoring text (e.g. "10+ years = 20 marks, 5-9 years = 12
marks, below 5 = 0") into a structured Rule (backend/models/rule.py), if the
RFP actually states one -- most criteria won't (eligibility gates, vague
qualitative ATC clauses with no marks table), and that's a legitimate,
common outcome, not an error.

Two LLM calls, mirroring extract_rfp_criteria.py's existing decomposition
style (guidance/mandatory/category are each their own simple call):
  1. A gate (classify(), cheap, closed-option) -- does this criterion state
     an explicit marks/points/threshold breakdown at all?
  2. Only if so, a shape extraction (extract_json(), open-ended) -- what does
     that breakdown actually look like, as a Rule-shaped JSON object?

The shape-extraction result is validated by attempting to parse it as a
Rule; any pydantic.ValidationError (including an intentionally empty {}
when the model couldn't confidently produce one) degrades to rule=None,
never raises -- same "don't guess" discipline used everywhere else in this
codebase (e.g. check_rfp_compliance.py never flags an uncited violation).
"""
from pydantic import TypeAdapter, ValidationError

from backend.llm.ollama_client import classify, extract_json
from backend.logging_config import get_logger
from backend.models.rule import Rule

logger = get_logger(__name__)

_RULE_ADAPTER = TypeAdapter(Rule)

_HAS_RULE_INSTRUCTION = (
    "ROLE: You are reviewing a single RFP criterion for whether it states an explicit scoring "
    "rule.\n"
    "OBJECTIVE: Decide whether the criterion's own text states an explicit marks/points/score "
    "breakdown for how a bidder's response should be scored.\n"
    "DECISION RULES:\n"
    "- Classify 'has_rule' only if the text itself states actual numbers tied to specific "
    "tiers, options, or a specific condition -- e.g. a numeric range broken into tiers each "
    "with its own stated score, a table mapping several specific named options each to a "
    "stated score, or an explicit point value awarded for meeting one specific stated "
    "condition. Example: a criterion stating 'N or more units = X marks, fewer = Y marks' is "
    "has_rule.\n"
    "- Classify 'no_rule' if the criterion is merely stated as mandatory or preferred, "
    "describes a specification or requirement, or expresses a preference/weightage in words "
    "without stating actual numbers tied to specific tiers or options.\n"
    "- A criterion that mentions marks, points, or weightage only in a general, non-itemized "
    "way (e.g. stating that responses 'will be evaluated and scored accordingly' without "
    "stating the breakdown itself) is 'no_rule' -- the actual numeric breakdown must be present "
    "in the text itself, not merely implied to exist elsewhere."
)

_SHAPE_EXTRACTION_INSTRUCTION = """ROLE: You are extracting a scoring rule's structure from a single RFP criterion's own text.
OBJECTIVE: This criterion states an explicit marks/points breakdown. Extract it as ONE of these two JSON shapes under "data" -- pick whichever actually matches the text, and use these exact field names.

Range (a numeric threshold broken into tiers, e.g. a quantity or a percentage with different marks at different levels):
{"type": "range", "field": "<short snake_case name for the quantity being measured>", "tiers": [{"min_value": <number or null>, "max_value": <number or null>, "score": <marks for this tier>}, ...]}
(min_value/max_value are null for an unbounded end -- e.g. a tier described as "N or more" is {"min_value": N, "max_value": null, "score": <marks>}. List every tier the text states, in the units the text itself uses.)

Lookup (a table of specific named options mapped to marks, or a binary yes/no condition mapped to marks):
{"type": "lookup", "field": "<short snake_case name for what's being looked up>", "table": {"<option>": <marks>, ...}, "default_score": <marks for anything not listed, usually 0>}
(For a binary condition, use table {"true": <marks>, "false": 0}.)

DECISION RULES:
- Use only the tiers, options, and numbers actually stated in the text -- never add a tier, option, or default that is not explicitly present.
- If you cannot confidently produce either shape from the text as actually written, respond with an empty object {} under "data" -- do not invent tiers, options, or numbers that aren't actually stated."""


def infer_rule(criterion_text: str) -> Rule | None:
    gate = classify(
        subject_text=criterion_text,
        references=[],
        verdict_options=["has_rule", "no_rule"],
        instruction=_HAS_RULE_INSTRUCTION,
    )
    if gate.verdict != "has_rule":
        return None

    extraction = extract_json(
        subject_text=criterion_text,
        instruction=_SHAPE_EXTRACTION_INSTRUCTION,
    )
    if not extraction.data:
        logger.info("infer_rule(): has_rule gate passed but shape extraction produced nothing usable")
        return None

    try:
        rule = _RULE_ADAPTER.validate_python(extraction.data)
    except ValidationError as e:
        logger.info(
            "infer_rule(): extracted shape failed validation (%s) -- degrading to no rule: %r", e, extraction.data
        )
        return None

    logger.info("infer_rule(): extracted %s rule for field %r", rule.type, rule.field)
    return rule


if __name__ == "__main__":
    # Milestone 5 verification -- run against a handful of representative
    # examples (the worked cases from the design plan, plus a plain
    # no-rule criterion) and inspect the output by eye against the source
    # text before trusting it. Real RFP clauses (data/rfps/*.pdf) should be
    # tried next, once these pass a basic sanity check.
    examples = [
        "The bidder must have a minimum of 5 years of relevant experience. 10 or more years of "
        "experience will be awarded 20 marks, 5-9 years will be awarded 12 marks, and less than 5 "
        "years is not eligible.",
        "The GPU offered will be scored as follows: NVIDIA H100 - 25 marks, NVIDIA A100 - 18 marks, "
        "any other GPU model - 0 marks.",
        "Bidders holding a valid ISO 27001 certification will be awarded an additional 10 marks.",
        "The bidder shall provide after-sales support for the duration of the contract.",
    ]
    for i, text in enumerate(examples, start=1):
        print(f"\n--- example {i} ---")
        print(text)
        rule = infer_rule(text)
        print(f"-> {rule!r}")
