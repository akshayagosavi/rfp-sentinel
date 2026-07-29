"""
M11: the shape retrieve_and_extract_evidence() produces -- one verdict per
(bid, criterion) pair, mirroring Criterion's compliance_issue/citation
fields but for "does this bid satisfy this requirement" instead of "does
this requirement conflict with a norm."
"""
from pydantic import BaseModel


class EvidenceItem(BaseModel):
    criterion_id: str
    bid_id: str
    verdict: str  # "pass" | "fail" | "partial" | "not_found"
    reasoning: str | None = None
    citation: dict | None = None  # {source_file, page_number, clause_ref}
    # Set only when this criterion has a Rule (see backend/models/rule.py) --
    # a criterion_evaluator.RuleResult.model_dump(), {score, max_score,
    # matched}. verdict above still drives the mandatory gate as always; for
    # a non-mandatory rule-scored criterion, verdict is only a coarse
    # presence indicator ("pass" if a value was extracted, "not_found" if
    # not), NOT a compliance judgment -- rule_result is the real signal,
    # consumed by score_stage1()'s weighted aggregation instead of
    # VERDICT_SCORE. None means "no rule, score from verdict" exactly as
    # before rules existed.
    rule_result: dict | None = None
