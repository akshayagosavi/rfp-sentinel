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
