"""
Admin-only endpoints. First capability: norm knowledge-base status control
(active/superseded/withdrawn) -- mark_status() has existed since M6/M7
(built for the supersede/withdraw mechanism), but never had a UI calling
it outside a one-off verification script. This is that UI's backend.

Second capability: user management -- list every registered account and
suspend/restore login access. Deactivation never deletes anything or
touches a user's past RFPs/bids, same non-destructive philosophy as norm
status transitions above.

Third capability: buyer-conduct oversight -- surfaces every published RFP
that has at least one criterion Checkpoint A flagged (a compliance_issue
or prohibited_practice_issue), together with the buyer's override_reasoning
for publishing anyway. No new storage: this data has existed on each
Criterion since Checkpoint A (see backend/graph/build_graph.py's
_checkpoint_a_node and frontend/src/components/EvaluationResult.jsx's
publish-with-overrides flow, which requires reasoning for every flagged
criterion before a flagged RFP can even be published) -- this is the first
place it's surfaced outside that one-time approval moment, for audit.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.auth import get_current_admin
from backend.db import get_user_by_id, list_all_users, list_published_rfps, set_user_active
from backend.rag.qdrant_client import get_client, list_norms, mark_status

router = APIRouter(prefix="/admin", tags=["admin"])

_VALID_STATUSES = {"active", "superseded", "withdrawn"}


@router.get("/norms")
def get_norms():
    return {"norms": list_norms(get_client())}


class UpdateNormStatusRequest(BaseModel):
    status: str


@router.post("/norms/{norm_name}/status")
def update_norm_status(norm_name: str, body: UpdateNormStatusRequest):
    if body.status not in _VALID_STATUSES:
        raise HTTPException(422, f"status must be one of {sorted(_VALID_STATUSES)}")
    mark_status(get_client(), norm_name, body.status)
    return {"norm_name": norm_name, "status": body.status}


@router.get("/users")
def get_users(request: Request):
    return {"users": list_all_users(request.app.state.db_pool)}


class SetUserActiveRequest(BaseModel):
    is_active: bool


@router.post("/users/{user_id}/active")
def set_user_active_endpoint(
    user_id: int, body: SetUserActiveRequest, request: Request, admin_email: str = Depends(get_current_admin),
):
    pool = request.app.state.db_pool
    target = get_user_by_id(pool, user_id)
    if target is None:
        raise HTTPException(404, "user not found")
    if not body.is_active and target["email"] == admin_email:
        raise HTTPException(400, "You cannot deactivate your own account")

    set_user_active(pool, user_id, body.is_active)
    return {"user_id": user_id, "is_active": body.is_active}


def _config(rfp_id: str) -> dict:
    return {"configurable": {"thread_id": rfp_id}}


@router.get("/flagged-rfps")
def get_flagged_rfps(request: Request):
    pool = request.app.state.db_pool
    graph = request.app.state.graph

    results = []
    for rfp in list_published_rfps(pool):
        state = graph.get_state(_config(rfp["rfp_id"]))
        if not state.values or not state.values.get("structured_rfp"):
            continue
        criteria = state.values["structured_rfp"].get("criteria", [])
        flagged = [c for c in criteria if c.get("compliance_issue") or c.get("prohibited_practice_issue")]
        if not flagged:
            continue
        results.append({
            "rfp_id": rfp["rfp_id"],
            "title": rfp["title"],
            "buyer_org": rfp["buyer_org"],
            "status": rfp["status"],
            "flagged_criteria": [
                {
                    "id": c["id"],
                    "text": c["text"],
                    "compliance_issue": c.get("compliance_issue"),
                    "compliance_citation": c.get("compliance_citation"),
                    "prohibited_practice_issue": c.get("prohibited_practice_issue"),
                    "prohibited_practice_citation": c.get("prohibited_practice_citation"),
                    "override_reasoning": c.get("override_reasoning"),
                }
                for c in flagged
            ],
        })
    return {"rfps": results}
