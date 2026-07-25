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
    evaluation_method: str = "L1"  # "L1" | "QCBS" -- extracted from the RFP's own "Evaluation Method" field
    price_band_percent: float | None = None  # MSE purchase-preference price band, e.g. "L-1+15%" -- this RFP's own number, not the 2012 Policy Order's general default
    mse_share_percent: float | None = None  # quantity share an MSE bidder gets if they match L-1 within the band above
    criteria: list[Criterion] = []
    required_documents: list[str] = []  # document TYPES the RFP says a bidder must submit
    prohibited_practices: list[str] = []  # GeM's own list of buyer drafting-mistakes that void the bid, extracted from this RFP's disclaimer page
    gem_bid_number: str | None = None  # GeM's own official bid reference (e.g. "GEM/2024/B/5735766"), distinct from our internal rfp_id
