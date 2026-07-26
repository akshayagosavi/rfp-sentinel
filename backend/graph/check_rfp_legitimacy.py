"""
Bidder-facing RFP legitimacy check -- confirms the norms/regulations an
RFP cites are still active (not superseded/withdrawn), reusing the same
norm-versioning infrastructure already built for bid evaluation
(mark_status()/list_norms(), M6-M7). Read-only: no new ingestion, just a
citation match against Qdrant's existing norms collection -- the same
data the admin norm-management screen already controls.

Citation detection is deterministic keyword matching per known norm, not
an LLM call -- verified against a real RFP first: it genuinely cites
GeM's GTC ("General Terms and Conditions"/"GTC"), the 2012 MSME Policy
Order ("Micro and Small Enterprises"), and the 2017 Make in India Order
("Make in India"), while NOT citing GFR 2017 or the CRS Handbook --
confirming citations are RFP-specific, not a fixed set every RFP
happens to mention. New norms added to the knowledge base later need a
matching keyword entry added here to be checkable; an uncited norm is
correctly just absent from the result, not an error.
"""
import pdfplumber

_NORM_CITATION_KEYWORDS = {
    "GeM General Terms and Conditions": ["General Terms and Conditions", "GTC"],
    "MSME Public Procurement Policy Order": ["Micro and Small Enterprises"],
    "DPIIT Public Procurement (Preference to Make in India) Order 2017": ["Make in India"],
    "GFR 2017 Chapter 6 (Procurement of Goods and Services)": ["GFR", "General Financial Rules"],
    "MeitY CRS Applicant Handbook": ["CRS", "Compulsory Registration Scheme"],
}


def check_rfp_legitimacy(pdf_path, norms: list[dict]) -> list[dict]:
    """norms: list_norms()'s output (see backend/rag/qdrant_client.py) --
    passed in rather than fetched here so callers already holding it (e.g.
    the same request also rendering the admin norm screen) don't pay for
    a second Qdrant round trip."""
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join((page.extract_text() or "") for page in pdf.pages)

    norms_by_name = {n["norm_name"]: n for n in norms}
    results = []
    for norm_name, keywords in _NORM_CITATION_KEYWORDS.items():
        if not any(kw in full_text for kw in keywords):
            continue
        norm = norms_by_name.get(norm_name)
        results.append({
            "norm_name": norm_name,
            "status": norm["status"] if norm else "unknown",
            "is_current": (norm["status"] == "active") if norm else None,
        })
    return results
