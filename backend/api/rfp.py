"""
Buyer-side RFP endpoints: upload -> background extraction + compliance
check -> Checkpoint A review -> approve -> resume.

Upload kicks off the slow part (LLM-heavy extract + compliance check) via
FastAPI's BackgroundTasks. Because that function is a plain sync def,
Starlette runs it in a thread pool automatically -- it does not block the
event loop, so /status polling keeps responding while it runs.
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile
from langgraph.types import Command
from pydantic import BaseModel

from backend.auth import get_current_buyer
from backend.db import (
    close_rfp,
    get_bid_evidence,
    get_rfp_record,
    get_stage1_results_for_rfp,
    list_rfps_by_buyer,
    publish_rfp,
    save_evidence_resolution,
    save_stage1_result,
    save_stage2_result,
)
from backend.graph.run_stage1_evaluation import run_stage1_evaluation
from backend.graph.run_stage2_evaluation import run_stage2_evaluation
from backend.models.evidence import EvidenceItem
from backend.models.rfp import StructuredRFP
from backend.scoring.scoring import BidInput, run_l1_selection, score_stage1

router = APIRouter(prefix="/rfp", tags=["rfp"])

RFP_DIR = Path("data/rfps")


def _config(rfp_id: str) -> dict:
    return {"configurable": {"thread_id": rfp_id}}


def _run_to_checkpoint_a(graph, initial_state: dict, config: dict) -> None:
    try:
        graph.invoke(initial_state, config)
    except Exception as e:
        # A node raised mid-run (e.g. the remote LLM became unreachable) --
        # LangGraph only checkpoints between completed nodes, so without this
        # the last-saved status (e.g. "checking_compliance") would sit there
        # forever, indistinguishable from still-in-progress. Write an explicit
        # terminal status so /status can tell the buyer it actually failed.
        graph.update_state(config, {"status": "failed", "error": str(e)})


@router.post("/upload")
async def upload_rfp(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile,
    max_criteria: int | None = None,  # testing-only cap; omit for a real, full run
):
    rfp_id = uuid.uuid4().hex[:8]
    dest = RFP_DIR / f"{rfp_id}_{file.filename}"
    dest.write_bytes(await file.read())

    initial_state = {
        "rfp_id": rfp_id,
        "pdf_path": str(dest),
        "structured_rfp": None,
        "status": "extracting",
        "max_criteria": max_criteria,
    }
    background_tasks.add_task(
        _run_to_checkpoint_a, request.app.state.graph, initial_state, _config(rfp_id)
    )
    return {"rfp_id": rfp_id, "status": "processing"}


@router.get("/{rfp_id}/status")
def get_status(rfp_id: str, request: Request):
    state = request.app.state.graph.get_state(_config(rfp_id))
    if not state.values:
        raise HTTPException(404, "rfp_id not found")
    return {
        "rfp_id": rfp_id,
        "status": state.values.get("status", "unknown"),
        "error": state.values.get("error"),
    }


@router.get("/{rfp_id}/criteria")
def get_criteria(rfp_id: str, request: Request):
    state = request.app.state.graph.get_state(_config(rfp_id))
    if not state.values or not state.values.get("structured_rfp"):
        raise HTTPException(404, "rfp_id not found, or criteria not ready yet")
    return {"rfp_id": rfp_id, "criteria": state.values["structured_rfp"]["criteria"]}


class ApproveRequest(BaseModel):
    criteria: list[dict]


@router.post("/{rfp_id}/criteria/approve")
def approve_criteria(
    rfp_id: str, body: ApproveRequest, request: Request, buyer_email: str = Depends(get_current_buyer)
):
    graph = request.app.state.graph
    config = _config(rfp_id)
    pending = graph.get_state(config).next
    if pending != ("checkpoint_a",):
        raise HTTPException(409, f"rfp_id is not awaiting Checkpoint A (next node(s): {pending})")

    # Server-side enforcement of the same rule the frontend's
    # publish-with-overrides flow already enforces client-side (see
    # EvaluationResult.jsx): a criterion flagged with a compliance_issue or
    # prohibited_practice_issue must carry a human's override_reasoning
    # before it can be published -- checked here too, not just in the
    # website's button logic, so a direct API call can't silently bypass
    # it. Found missing during a live check of the buyer-conduct oversight
    # admin view: this endpoint previously trusted any payload it was given.
    unjustified = [
        c["id"] for c in body.criteria
        if (c.get("compliance_issue") or c.get("prohibited_practice_issue")) and not c.get("override_reasoning")
    ]
    if unjustified:
        raise HTTPException(422, {
            "message": "Flagged criteria must have override_reasoning before this RFP can be published.",
            "unjustified_criteria": unjustified,
        })

    graph.invoke(Command(resume=body.criteria), config)

    # This is the real "publish" moment -- write the queryable metadata row
    # the public /bids listing reads from (LangGraph's checkpoint state
    # still holds the full criteria/evidence, this is just what's needed
    # to search/filter/display it without touching that state).
    structured_rfp = graph.get_state(config).values["structured_rfp"]
    publish_rfp(
        request.app.state.db_pool, rfp_id, buyer_email,
        title=structured_rfp["source_file"], category=structured_rfp["category"],
        gem_bid_number=structured_rfp.get("gem_bid_number"),
    )

    return {"rfp_id": rfp_id, "status": "approved"}


@router.get("/mine")
def list_my_rfps(request: Request, buyer_email: str = Depends(get_current_buyer)):
    return {"rfps": list_rfps_by_buyer(request.app.state.db_pool, buyer_email)}


@router.post("/{rfp_id}/close")
def close_and_evaluate(rfp_id: str, background_tasks: BackgroundTasks, request: Request):
    """The manual "Close & Evaluate Now" override -- the same transition the
    closing_date timer applies automatically (see backend/main.py's
    _closing_timer_loop), just triggered on demand so a demo doesn't have to
    wait out the real multi-day bid period. Closes submissions immediately,
    then runs Stage 1 (technical gate) for every bid already on file -- see
    run_stage1_evaluation's module docstring for why Stage 2 isn't included."""
    pool = request.app.state.db_pool
    record = get_rfp_record(pool, rfp_id)
    if record is None:
        raise HTTPException(404, "rfp_id not found")
    if record["status"] != "published":
        raise HTTPException(409, f"RFP is not open for closing (status: {record['status']})")

    if not close_rfp(pool, rfp_id):
        raise HTTPException(409, "RFP was already closed by someone else")

    graph = request.app.state.graph
    state = graph.get_state(_config(rfp_id))
    structured_rfp = StructuredRFP.model_validate(state.values["structured_rfp"])
    background_tasks.add_task(run_stage1_evaluation, pool, rfp_id, structured_rfp)

    return {"rfp_id": rfp_id, "status": "closed", "evaluation": "started"}


@router.get("/{rfp_id}/evaluation")
def get_evaluation(rfp_id: str, request: Request):
    pool = request.app.state.db_pool
    record = get_rfp_record(pool, rfp_id)
    if record is None:
        raise HTTPException(404, "rfp_id not found")
    return {
        "rfp_id": rfp_id, "rfp_status": record["status"],
        "bids": get_stage1_results_for_rfp(pool, rfp_id),
        "stage2_result": record["stage2_result"],
    }


@router.post("/{rfp_id}/open-financial-bids")
def open_financial_bids(rfp_id: str, background_tasks: BackgroundTasks, request: Request):
    """Stage 2's trigger -- deliberately separate from /close, not automatic
    after Stage 1 finishes. Real two-envelope procurement only opens a
    bidder's price once technical evaluation has fully concluded, and only
    for bidders who actually passed it; this endpoint enforces both.

    Also blocks on any Stage-1-passed bid that still has unresolved
    pending_criteria -- a mandatory criterion the model couldn't find
    evidence for either way (not_found) is held for human review, never
    auto-passed (see score_stage1's docstring). Letting a bid through to
    financial ranking with open questions on its mandatory criteria would
    silently defeat that review, so this is the actual enforcement point."""
    pool = request.app.state.db_pool
    record = get_rfp_record(pool, rfp_id)
    if record is None:
        raise HTTPException(404, "rfp_id not found")
    if record["status"] != "closed":
        raise HTTPException(409, f"RFP must be closed with Stage 1 complete first (status: {record['status']})")

    bids = get_stage1_results_for_rfp(pool, rfp_id)
    if any(b["status"] in ("submitted", "under_evaluation") for b in bids):
        raise HTTPException(409, "Stage 1 evaluation is still in progress for one or more bids")
    if any(b["status"] == "stage1_passed" and b["pending_criteria"] for b in bids):
        raise HTTPException(
            409,
            "One or more Stage-1-passed bids still have unresolved mandatory criteria -- "
            "resolve them (POST .../evidence/{criterion_id}/resolve) before opening financial bids",
        )

    graph = request.app.state.graph
    state = graph.get_state(_config(rfp_id))
    structured_rfp = StructuredRFP.model_validate(state.values["structured_rfp"])

    background_tasks.add_task(run_stage2_evaluation, pool, rfp_id, structured_rfp)
    return {"rfp_id": rfp_id, "status": "opening_financial_bids"}


class ResolveEvidenceRequest(BaseModel):
    verdict: str  # "pass" or "fail" -- the buyer's human judgment call
    reasoning: str


@router.post("/{rfp_id}/bids/{bid_id}/evidence/{criterion_id}/resolve")
def resolve_pending_evidence(
    rfp_id: str, bid_id: str, criterion_id: str, body: ResolveEvidenceRequest, request: Request,
):
    """A buyer resolving one 'not_found' mandatory criterion by hand --
    same audit-trail discipline as Checkpoint A's override_reasoning
    (required reasoning, permanently stored alongside the decision, never
    a silent auto-decision). Recomputes the bid's full Stage 1 result
    afterward, exactly the same score_stage1() call run_stage1_evaluation
    uses, just fed the updated (resolved) evidence -- not a parallel,
    separately-maintained calculation."""
    if body.verdict not in ("pass", "fail"):
        raise HTTPException(422, "verdict must be 'pass' or 'fail'")
    if not body.reasoning.strip():
        raise HTTPException(422, "reasoning is required")

    pool = request.app.state.db_pool
    record = get_rfp_record(pool, rfp_id)
    if record is None:
        raise HTTPException(404, "rfp_id not found")

    save_evidence_resolution(pool, bid_id, criterion_id, body.verdict, body.reasoning)

    graph = request.app.state.graph
    state = graph.get_state(_config(rfp_id))
    structured_rfp = StructuredRFP.model_validate(state.values["structured_rfp"])

    evidence = [
        EvidenceItem(criterion_id=e["criterion_id"], bid_id=bid_id, verdict=e["effective_verdict"],
                     reasoning=e["reasoning"], citation=e["citation"])
        for e in get_bid_evidence(pool, bid_id)
    ]
    result = score_stage1(structured_rfp.criteria, evidence)
    save_stage1_result(pool, bid_id, result.model_dump())

    return {
        "bid_id": bid_id, "criterion_id": criterion_id, "resolved_verdict": body.verdict,
        "stage1_passed": result.passed, "pending_remaining": result.pending_criteria,
    }


class RunL1SelectionRequest(BaseModel):
    mse_preference_active: bool = True


@router.post("/{rfp_id}/run-l1-selection")
def run_l1_selection_endpoint(rfp_id: str, body: RunL1SelectionRequest, request: Request):
    """Mirrors GeM's own buyer-triggered "Run L1 selection" feature -- only
    meaningful once Stage 2 found a genuine price tie (see
    backend/scoring/scoring.py's run_l1_selection() for the real mechanism
    this wraps)."""
    pool = request.app.state.db_pool
    record = get_rfp_record(pool, rfp_id)
    if record is None:
        raise HTTPException(404, "rfp_id not found")
    stage2 = record["stage2_result"]
    if record["status"] != "evaluated" or not stage2 or not stage2.get("tied_for_l1"):
        raise HTTPException(409, "No L1 tie to resolve for this RFP")

    bids = get_stage1_results_for_rfp(pool, rfp_id)
    bid_inputs = [
        BidInput(bid_id=b["bid_id"], price=b["price"], is_mii_local=b["is_mii_local"], is_mse=b["is_mse"])
        for b in bids if b["price"] is not None
    ]
    winner = run_l1_selection(stage2["tied_for_l1"], bid_inputs, body.mse_preference_active)
    stage2["l1_winner"] = winner
    stage2["l1_selection_mse_preference_active"] = body.mse_preference_active
    save_stage2_result(pool, rfp_id, stage2)

    return {"rfp_id": rfp_id, "l1_winner": winner}
