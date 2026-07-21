"""
PLACEHOLDER compliance layer for the demo.

The real design (per README/ROADMAP) is a LangGraph multi-agent RAG pipeline
querying norms in Qdrant. That agent layer isn't built yet (backend/rag/ is
still empty), so this module is a small keyword/rule-based stand-in that runs
against the *real* extracted+chunked text from the uploaded PDF. It exists
purely so the pipeline has something to show end-to-end tomorrow.

Swap `check_rfp_against_rules()` and `evaluate_bid_against_rfp()` for calls
into backend/rag/ once the agent graph exists. The output shape
(ComplianceIssue / list[ComplianceIssue]) is designed to stay stable across
that swap so the frontend doesn't need to change.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from ingestion.chunker import Chunk

# Each rule: (id, human label, keywords that should appear SOMEWHERE in the
# document for the clause to be considered "present", severity, norm citation)
RFP_RULES = [
    dict(
        id="mse-purchase-preference",
        label="MSE purchase preference / exemption clause",
        keywords=["micro and small enterprise", "mse", "udyam", "purchase preference"],
        severity="high",
        norm="Public Procurement Policy for MSEs Order, 2012",
    ),
    dict(
        id="emd-exemption",
        label="EMD exemption for registered MSEs / startups",
        keywords=["emd", "earnest money"],
        severity="medium",
        norm="Public Procurement Policy for MSEs Order, 2012",
    ),
    dict(
        id="gem-gtc-reference",
        label="Reference to GeM General Terms & Conditions",
        keywords=["general terms and conditions", "gtc", "gem portal"],
        severity="high",
        norm="GeM GTC v1.8",
    ),
    dict(
        id="bis-standard",
        label="BIS / technical standard citation for the item specification",
        keywords=["bis", "is 13252", "bureau of indian standards", "certification"],
        severity="medium",
        norm="Handbook - Testing / BIS standards",
    ),
    dict(
        id="delivery-timeline",
        label="Delivery timeline clause",
        keywords=["delivery period", "days from", "date of order", "lead time"],
        severity="medium",
        norm="GeM GTC v1.8",
    ),
    dict(
        id="payment-terms",
        label="Payment terms clause",
        keywords=["payment terms", "payment shall be made", "invoice"],
        severity="low",
        norm="GeM GTC v1.8",
    ),
]


@dataclass
class ComplianceIssue:
    rule_id: str
    label: str
    status: str  # "present" | "missing"
    severity: str
    norm: str
    matched_snippet: str | None = None
    page_number: int | None = None


def _full_text_lower(chunks: list[Chunk]) -> str:
    return "\n".join(c.text for c in chunks).lower()


def _find_snippet(chunks: list[Chunk], keyword: str) -> tuple[str | None, int | None]:
    for c in chunks:
        idx = c.text.lower().find(keyword)
        if idx != -1:
            start = max(0, idx - 40)
            end = min(len(c.text), idx + len(keyword) + 60)
            return c.text[start:end].strip(), c.page_number
    return None, None


def check_rfp_against_rules(chunks: list[Chunk]) -> list[ComplianceIssue]:
    """Placeholder norm-compliance check for a draft RFP."""
    full_text = _full_text_lower(chunks)
    issues: list[ComplianceIssue] = []
    for rule in RFP_RULES:
        hit_keyword = next((kw for kw in rule["keywords"] if kw in full_text), None)
        if hit_keyword:
            snippet, page = _find_snippet(chunks, hit_keyword)
            issues.append(ComplianceIssue(
                rule_id=rule["id"], label=rule["label"], status="present",
                severity=rule["severity"], norm=rule["norm"],
                matched_snippet=snippet, page_number=page,
            ))
        else:
            issues.append(ComplianceIssue(
                rule_id=rule["id"], label=rule["label"], status="missing",
                severity=rule["severity"], norm=rule["norm"],
            ))
    return issues


def evaluate_bid_against_rfp(rfp_chunks: list[Chunk], bid_chunks: list[Chunk]) -> list[ComplianceIssue]:
    """Placeholder: for each RFP clause chunk, check whether the bid document
    appears to address it (naive keyword-overlap), rather than a real
    evidence-extraction agent."""
    bid_text = _full_text_lower(bid_chunks)
    issues: list[ComplianceIssue] = []
    for c in rfp_chunks:
        if c.chunk_type != "prose" or len(c.text.split()) < 8:
            continue
        words = [w.strip(".,()") for w in c.text.lower().split() if len(w) > 5]
        significant = list(dict.fromkeys(words))[:6]
        if not significant:
            continue
        overlap = sum(1 for w in significant if w in bid_text)
        addressed = overlap >= max(2, len(significant) // 2)
        label = c.clause_ref or f"Clause on page {c.page_number}"
        issues.append(ComplianceIssue(
            rule_id=f"rfp-clause-{c.page_number}-{label}",
            label=f"Bid response to: {label}",
            status="present" if addressed else "missing",
            severity="medium",
            norm="Bidder responsiveness (naive keyword match, not a real evidence agent)",
            matched_snippet=c.text[:140].strip(),
            page_number=c.page_number,
        ))
    return issues


def issue_to_dict(issue: ComplianceIssue) -> dict:
    return asdict(issue)
