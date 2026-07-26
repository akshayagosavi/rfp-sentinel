"""
Bidder-facing endpoints -- what a SIGNED-IN bidder needs about their OWN
activity. Browsing published bids is public (see backend/api/bids.py);
this file covers "my submitted bids" and the actual submission itself.

Submission enforces the upload-time completeness check as a hard block --
our deliberate improvement over real GeM, which silently invalidates a bid
with a missing document with no warning at all. This must stay a BLOCK,
not a post-hoc flag: unlike check_document_completeness's other use (a
buyer-side, non-blocking review of an already-closed bid that can't be
fixed anymore), here the bidder can still fix it and resubmit before the
deadline, so there's no reason to accept a submission we already know is
incomplete.
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from backend.auth import get_current_bidder
from backend.db import create_bid_record, get_rfp_record, has_bidder_applied, list_bidder_bids
from backend.graph.check_document_completeness import check_document_completeness
from backend.rag.qdrant_client import ensure_bids_collection, get_client
from ingestion.ingest_bid import ingest_bid

router = APIRouter(prefix="/bidder", tags=["bidder"])

BID_DIR = Path("data/bids")


def _config(rfp_id: str) -> dict:
    return {"configurable": {"thread_id": rfp_id}}


@router.get("/my-bids")
def my_bids(request: Request, bidder_email: str = Depends(get_current_bidder)):
    return {"bids": list_bidder_bids(request.app.state.db_pool, bidder_email)}


@router.post("/bids/{rfp_id}/submit")
async def submit_bid(
    rfp_id: str,
    request: Request,
    files: list[UploadFile] = File(...),  # technical/eligibility documents -- Packet-I
    financial_document: UploadFile = File(...),  # price schedule / financial bid -- Packet-II, sealed
    bidder_email: str = Depends(get_current_bidder),
):
    pool = request.app.state.db_pool

    record = get_rfp_record(pool, rfp_id)
    if record is None or record["status"] != "published":
        raise HTTPException(404, "This bid is not open for submission")

    if has_bidder_applied(pool, rfp_id, bidder_email):
        raise HTTPException(409, "You have already submitted a bid for this RFP")

    state = request.app.state.graph.get_state(_config(rfp_id))
    structured_rfp = state.values.get("structured_rfp") if state.values else None
    if not structured_rfp:
        raise HTTPException(404, "RFP criteria not found")
    required_documents = structured_rfp.get("required_documents", [])

    # The blocking completeness check -- deterministic, no LLM, reused
    # as-is from the buyer-side non-blocking version (backend.graph.
    # check_document_completeness). Same function, different consequence,
    # because the moment in the timeline is different (see module docstring).
    # Only the technical documents are checked -- required_documents are all
    # Packet-I types; the financial document is mandatory structurally
    # (every bid needs one), not something the RFP's own list enumerates.
    uploaded_filenames = [f.filename for f in files]
    completeness = check_document_completeness(required_documents, uploaded_filenames)
    if completeness["missing"]:
        raise HTTPException(422, {
            "message": "Submission incomplete -- fix the files below and resubmit.",
            "missing": completeness["missing"],
            "present": [item["required"] for item in completeness["present"]],
        })

    bid_id = uuid.uuid4().hex[:8]
    bid_dir = BID_DIR / bid_id
    bid_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    for f in files:
        dest = bid_dir / f.filename
        dest.write_bytes(await f.read())
        saved_files.append(("I", dest))

    financial_dest = bid_dir / financial_document.filename
    financial_dest.write_bytes(await financial_document.read())
    saved_files.append(("II", financial_dest))  # sealed -- search_bid() defaults to packet="I", never sees this

    client = get_client()
    ensure_bids_collection(client)
    ingest_bid(client, bid_id, rfp_id, bidder_email, saved_files)

    create_bid_record(pool, bid_id, rfp_id, bidder_email)

    return {"bid_id": bid_id, "status": "submitted"}
