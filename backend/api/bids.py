"""
Public bid-listing endpoints -- no login required to browse, matching real
GeM (anyone can see a published tender) and this project's own design
decision: browsing is public, only "Apply" needs an account. Supersedes
the earlier bidder-only listing/detail in bidder.py, which now handles a
signed-in bidder's OWN submitted bids instead (a different, narrower job).

Metadata (title, category, closing_date, status, buyer org) comes from the
real `rfps` Postgres table (backend/db.py) so it's actually searchable and
filterable -- the full criteria/required-documents detail still comes from
LangGraph's checkpoint state, same source bidder.py always used.
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from backend.db import get_rfp_record, list_published_rfps, save_rfp_summary
from backend.graph.check_rfp_legitimacy import check_rfp_legitimacy
from backend.graph.generate_rfp_summary import generate_rfp_summary
from backend.models.rfp import StructuredRFP
from backend.rag.qdrant_client import get_client, list_norms

router = APIRouter(prefix="/bids", tags=["bids"])

RFP_DIR = Path("data/rfps")


def _config(rfp_id: str) -> dict:
    return {"configurable": {"thread_id": rfp_id}}


@router.get("")
def browse_bids(request: Request, keyword: str | None = None, category: str | None = None, status: str | None = None):
    return {"bids": list_published_rfps(request.app.state.db_pool, keyword, category, status)}


@router.get("/{rfp_id}")
def get_bid_detail(rfp_id: str, request: Request):
    record = get_rfp_record(request.app.state.db_pool, rfp_id)
    if record is None:
        raise HTTPException(404, "Bid not found")

    state = request.app.state.graph.get_state(_config(rfp_id))
    rfp = state.values.get("structured_rfp") if state.values else None
    if not rfp:
        raise HTTPException(404, "Bid not found")

    mandatory_count = sum(1 for c in rfp["criteria"] if c["mandatory"])
    return {
        **record,
        "evaluation_method": rfp["evaluation_method"],
        "criteria_count": len(rfp["criteria"]),
        "mandatory_criteria_count": mandatory_count,
        "required_documents": rfp.get("required_documents", []),
    }


@router.get("/{rfp_id}/document")
def download_bid_document(rfp_id: str, request: Request):
    record = get_rfp_record(request.app.state.db_pool, rfp_id)
    if record is None:
        raise HTTPException(404, "Bid not found")
    # record["title"] is the on-disk filename (rfp_id + original name),
    # set once at upload time by our own code -- not attacker-controlled
    # input, safe to build a path from directly.
    path = RFP_DIR / record["title"]
    if not path.exists():
        raise HTTPException(404, "Document file not found")
    return FileResponse(path, media_type="application/pdf", filename=record["title"])


@router.get("/{rfp_id}/legitimacy-check")
def get_legitimacy_check(rfp_id: str, request: Request):
    """Confirms the norms this RFP cites are still active -- read-only
    check against the same norm knowledge base the admin norm-management
    screen controls (see check_rfp_legitimacy.py's docstring for the
    citation-detection approach)."""
    record = get_rfp_record(request.app.state.db_pool, rfp_id)
    if record is None:
        raise HTTPException(404, "Bid not found")
    path = RFP_DIR / record["title"]
    if not path.exists():
        raise HTTPException(404, "Document file not found")
    norms = list_norms(get_client())
    return {"rfp_id": rfp_id, "citations": check_rfp_legitimacy(path, norms)}


@router.get("/{rfp_id}/summary")
def get_rfp_summary(rfp_id: str, request: Request):
    """Generated once, cached in Postgres from then on -- see
    generate_rfp_summary.py's docstring for why."""
    record = get_rfp_record(request.app.state.db_pool, rfp_id)
    if record is None:
        raise HTTPException(404, "Bid not found")
    if record["summary"]:
        return {"rfp_id": rfp_id, "summary": record["summary"]}

    state = request.app.state.graph.get_state(_config(rfp_id))
    structured_rfp_dict = state.values.get("structured_rfp") if state.values else None
    if not structured_rfp_dict:
        raise HTTPException(404, "Bid not found")

    structured_rfp = StructuredRFP.model_validate(structured_rfp_dict)
    try:
        summary = generate_rfp_summary(structured_rfp)
    except RuntimeError as e:
        raise HTTPException(503, f"Could not generate a summary right now: {e}")

    save_rfp_summary(request.app.state.db_pool, rfp_id, summary)
    return {"rfp_id": rfp_id, "summary": summary}
