"""
Bidder-facing RFP endpoints -- read-only. A bidder should never have to
open the RFP PDF themselves just to find out what documents to submit;
these two endpoints answer "what's open to bid on" and "what exactly does
this one require," using data already produced by the buyer-side pipeline
(extract_rfp_criteria's structured_rfp, including required_documents).

No new persistence added: "published" RFPs are found by scanning
data/rfps/ for uploaded files and checking each one's graph status is
"approved" -- the same status the buyer flow already sets at Checkpoint A.
A dedicated `rfps` table (per the original plan) is the real long-term
answer once evaluation volume makes a directory scan too slow; not needed
at today's scale.
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/bidder", tags=["bidder"])

RFP_DIR = Path("data/rfps")


def _config(rfp_id: str) -> dict:
    return {"configurable": {"thread_id": rfp_id}}


def _iter_rfp_ids():
    seen = set()
    for path in RFP_DIR.glob("*_*"):
        rfp_id = path.name.split("_", 1)[0]
        if rfp_id not in seen:
            seen.add(rfp_id)
            yield rfp_id


@router.get("/rfps")
def list_published_rfps(request: Request):
    graph = request.app.state.graph
    published = []
    for rfp_id in _iter_rfp_ids():
        state = graph.get_state(_config(rfp_id))
        rfp = state.values.get("structured_rfp") if state.values else None
        if not rfp or state.values.get("status") != "approved":
            continue
        published.append({
            "rfp_id": rfp_id,
            "source_file": rfp["source_file"],
            "category": rfp["category"],
            "evaluation_method": rfp["evaluation_method"],
            "criteria_count": len(rfp["criteria"]),
            "required_documents_count": len(rfp.get("required_documents", [])),
        })
    return {"rfps": published}


@router.get("/rfps/{rfp_id}")
def get_rfp_summary(rfp_id: str, request: Request):
    state = request.app.state.graph.get_state(_config(rfp_id))
    rfp = state.values.get("structured_rfp") if state.values else None
    if not rfp or state.values.get("status") != "approved":
        raise HTTPException(404, "rfp_id not found, or not yet published")

    mandatory_count = sum(1 for c in rfp["criteria"] if c["mandatory"])
    return {
        "rfp_id": rfp_id,
        "source_file": rfp["source_file"],
        "category": rfp["category"],
        "evaluation_method": rfp["evaluation_method"],
        "criteria_count": len(rfp["criteria"]),
        "mandatory_criteria_count": mandatory_count,
        "required_documents": rfp.get("required_documents", []),
    }
