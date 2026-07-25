"""
M9: the shapes extract_rfp_criteria() and check_rfp_compliance() work with.
"""
from pydantic import BaseModel


class Criterion(BaseModel):
    id: str
    text: str
    mandatory: bool
    category: str  # "technical" | "financial" | "eligibility"
    page_number: int
    clause_ref: str | None = None
    compliance_issue: str | None = None
    compliance_citation: dict | None = None
    override_reasoning: str | None = None  # set when a human overrides a flagged issue and publishes anyway
    prohibited_practice_issue: str | None = None  # this criterion appears to match one of the RFP's own listed buyer prohibited-practices
    prohibited_practice_citation: dict | None = None


class StructuredRFP(BaseModel):
    rfp_id: str
    source_file: str
    category: str = "Electronics"
    evaluation_method: str = "L1"  # "L1" | "QCBS"
    criteria: list[Criterion] = []
    required_documents: list[str] = []  # document TYPES the RFP says a bidder must submit
    prohibited_practices: list[str] = []  # GeM's own list of buyer drafting-mistakes that void the bid, extracted from this RFP's disclaimer page
