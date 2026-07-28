"""
Buyer-side RFP endpoints: upload -> background extraction + compliance
check -> Checkpoint A review -> approve -> resume.

Upload kicks off the slow part (LLM-heavy extract + compliance check) via
FastAPI's BackgroundTasks. Because that function is a plain sync def,
Starlette runs it in a thread pool automatically -- it does not block the
event loop, so /status polling keeps responding while it runs.
"""
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from langgraph.types import Command
from pydantic import BaseModel

from backend.auth import get_current_buyer
from backend.db import (
    close_rfp,
    delete_rfp,
    get_bid_evidence,
    get_rfp_record,
    get_stage1_results_for_rfp,
    list_bid_ids_for_rfp,
    list_rfp_flags,
    list_rfps_by_buyer,
    publish_rfp,
    resolve_rfp_flag,
    save_evidence_resolution,
    save_stage1_result,
    save_stage2_result,
)
from backend.graph.check_document_completeness import check_document_completeness
from backend.graph.run_stage1_evaluation import run_stage1_evaluation
from backend.graph.run_stage2_evaluation import run_stage2_evaluation
from backend.models.evidence import EvidenceItem
from backend.models.rfp import StructuredRFP
from backend.rag.qdrant_client import delete_bid_chunks, get_bid_source_files, get_client
from backend.scoring.scoring import BidInput, run_l1_selection, score_stage1

router = APIRouter(prefix="/rfp", tags=["rfp"])

RFP_DIR = Path("data/rfps")
BID_DIR = Path("data/bids")


def _config(rfp_id: str) -> dict:
    return {"configurable": {"thread_id": rfp_id}}


def _require_owner(actual_email: str | None, calling_email: str) -> None:
    """The real fix for 'any buyer can manage any other buyer's RFP' --
    rfps.buyer_user_id (and, pre-publish, the graph state's buyer_email)
    already recorded who owns each RFP; nothing ever checked it before.
    actual_email is None only for an RFP that predates this field existing
    at all -- permissive there rather than locking out already-in-flight
    work with no way to fix it; strict (403) everywhere else."""
    if actual_email is not None and actual_email != calling_email:
        raise HTTPException(403, "You don't have access to this RFP")


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
    buyer_email: str = Depends(get_current_buyer),
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
        "buyer_email": buyer_email,
    }
    background_tasks.add_task(
        _run_to_checkpoint_a, request.app.state.graph, initial_state, _config(rfp_id)
    )
    return {"rfp_id": rfp_id, "status": "processing"}


@router.get("/{rfp_id}/status")
def get_status(rfp_id: str, request: Request, buyer_email: str = Depends(get_current_buyer)):
    state = request.app.state.graph.get_state(_config(rfp_id))
    if not state.values:
        raise HTTPException(404, "rfp_id not found")
    _require_owner(state.values.get("buyer_email"), buyer_email)
    return {
        "rfp_id": rfp_id,
        "status": state.values.get("status", "unknown"),
        "error": state.values.get("error"),
    }


@router.get("/{rfp_id}/criteria")
def get_criteria(rfp_id: str, request: Request, buyer_email: str = Depends(get_current_buyer)):
    state = request.app.state.graph.get_state(_config(rfp_id))
    if not state.values or not state.values.get("structured_rfp"):
        raise HTTPException(404, "rfp_id not found, or criteria not ready yet")
    _require_owner(state.values.get("buyer_email"), buyer_email)
    return {"rfp_id": rfp_id, "criteria": state.values["structured_rfp"]["criteria"]}


class ApproveRequest(BaseModel):
    criteria: list[dict]


@router.post("/{rfp_id}/criteria/approve")
def approve_criteria(
    rfp_id: str, body: ApproveRequest, request: Request, buyer_email: str = Depends(get_current_buyer)
):
    graph = request.app.state.graph
    config = _config(rfp_id)
    state = graph.get_state(config)
    _require_owner(state.values.get("buyer_email") if state.values else None, buyer_email)
    pending = state.next
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


@router.delete("/{rfp_id}")
def delete_rfp_endpoint(rfp_id: str, request: Request, buyer_email: str = Depends(get_current_buyer)):
    """Buyer-triggered hard delete -- a testing/reset convenience, not a
    routine production action. Only allowed in the two cases that can't
    destroy in-progress work: no bids have been submitted yet (nothing to
    lose), or evaluation has already fully concluded (status='evaluated',
    nothing left in flight). An RFP sitting between those two states --
    published with live submissions, or closed and partway through Stage 1/
    Stage 2 -- is refused, matching this project's standing discipline of
    never destroying real, in-progress evaluation data (same reasoning as
    deactivating a user instead of deleting them, or marking a norm
    superseded instead of removing it)."""
    pool = request.app.state.db_pool
    record = get_rfp_record(pool, rfp_id)
    if record is None:
        raise HTTPException(404, "rfp_id not found")
    _require_owner(record["buyer_email"], buyer_email)

    bid_ids = list_bid_ids_for_rfp(pool, rfp_id)
    if bid_ids and record["status"] != "evaluated":
        raise HTTPException(
            409,
            "This RFP has submitted bids and evaluation isn't finished -- "
            "can't delete it until Stage 1/Stage 2 complete, or until it has no bids at all.",
        )

    client = get_client()
    for bid_id in bid_ids:
        delete_bid_chunks(client, bid_id)
        bid_dir = BID_DIR / bid_id
        if bid_dir.exists():
            shutil.rmtree(bid_dir)

    delete_rfp(pool, rfp_id)
    request.app.state.graph.checkpointer.delete_thread(rfp_id)

    rfp_path = RFP_DIR / record["title"]
    if rfp_path.exists():
        rfp_path.unlink()

    return {"rfp_id": rfp_id, "status": "deleted"}


@router.post("/{rfp_id}/close")
def close_and_evaluate(
    rfp_id: str, background_tasks: BackgroundTasks, request: Request,
    buyer_email: str = Depends(get_current_buyer),
):
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
    _require_owner(record["buyer_email"], buyer_email)
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
def get_evaluation(rfp_id: str, request: Request, buyer_email: str = Depends(get_current_buyer)):
    pool = request.app.state.db_pool
    record = get_rfp_record(pool, rfp_id)
    if record is None:
        raise HTTPException(404, "rfp_id not found")
    _require_owner(record["buyer_email"], buyer_email)
    return {
        "rfp_id": rfp_id, "rfp_status": record["status"],
        "bids": get_stage1_results_for_rfp(pool, rfp_id),
        "stage2_result": record["stage2_result"],
    }


@router.get("/{rfp_id}/flags")
def get_rfp_flags(rfp_id: str, request: Request, buyer_email: str = Depends(get_current_buyer)):
    """Bidder-raised pre-bid queries/concerns for this RFP -- see rfp_flags'
    schema comment (backend/db.py) for why this is a separate audit trail
    from the Checkpoint A compliance flags surfaced to admin."""
    pool = request.app.state.db_pool
    record = get_rfp_record(pool, rfp_id)
    if record is None:
        raise HTTPException(404, "rfp_id not found")
    _require_owner(record["buyer_email"], buyer_email)
    return {"flags": list_rfp_flags(pool, rfp_id)}


class ResolveFlagRequest(BaseModel):
    resolution_note: str


@router.post("/{rfp_id}/flags/{flag_id}/resolve")
def resolve_flag_endpoint(
    rfp_id: str, flag_id: int, body: ResolveFlagRequest, request: Request,
    buyer_email: str = Depends(get_current_buyer),
):
    if not body.resolution_note.strip():
        raise HTTPException(422, "resolution_note is required")
    pool = request.app.state.db_pool
    record = get_rfp_record(pool, rfp_id)
    if record is None:
        raise HTTPException(404, "rfp_id not found")
    _require_owner(record["buyer_email"], buyer_email)
    if not resolve_rfp_flag(pool, flag_id, body.resolution_note.strip()):
        raise HTTPException(404, "flag_id not found")
    return {"flag_id": flag_id, "status": "resolved"}


@router.get("/{rfp_id}/bids/{bid_id}/documents")
def get_bid_documents(
    rfp_id: str, bid_id: str, request: Request, buyer_email: str = Depends(get_current_buyer),
):
    """Lets the buyer actually see what a bidder submitted -- previously
    there was no way to do this at all; a buyer resolving a pending
    mandatory criterion was told to "review the bid's documents" with no
    means to do so. Reuses check_document_completeness() (already built,
    already used as a hard block at bidder submission time) to also answer
    "which required document types is this bid missing" here, non-blocking,
    for the buyer's own review.

    Packet-II (financial) stays sealed -- listed as present only once this
    RFP's stage2_result actually exists (financial bids fully opened and
    ranked), never before. This mirrors search_bid()'s own packet="I"
    default and extract_bid_price()'s status as the only caller ever
    requesting packet="II" -- the seal is enforced here the same way, not
    left to trust."""
    pool = request.app.state.db_pool
    record = get_rfp_record(pool, rfp_id)
    if record is None:
        raise HTTPException(404, "rfp_id not found")
    _require_owner(record["buyer_email"], buyer_email)
    if bid_id not in list_bid_ids_for_rfp(pool, rfp_id):
        raise HTTPException(404, "bid_id not found for this rfp_id")

    client = get_client()
    packet_i_files = get_bid_source_files(client, bid_id, packet="I")
    sealed = record["stage2_result"] is None
    packet_ii_files = [] if sealed else get_bid_source_files(client, bid_id, packet="II")

    state = request.app.state.graph.get_state(_config(rfp_id))
    structured_rfp = state.values.get("structured_rfp") if state.values else None
    required_documents = structured_rfp.get("required_documents", []) if structured_rfp else []
    completeness = check_document_completeness(required_documents, packet_i_files)

    return {
        "bid_id": bid_id,
        "packet_i_files": packet_i_files,
        "packet_ii_files": packet_ii_files,
        "packet_ii_sealed": sealed,
        "completeness": completeness,
    }


@router.get("/{rfp_id}/bids/{bid_id}/documents/{filename}")
def download_bid_document(
    rfp_id: str, bid_id: str, filename: str, request: Request,
    buyer_email: str = Depends(get_current_buyer),
):
    pool = request.app.state.db_pool
    record = get_rfp_record(pool, rfp_id)
    if record is None:
        raise HTTPException(404, "rfp_id not found")
    _require_owner(record["buyer_email"], buyer_email)
    if bid_id not in list_bid_ids_for_rfp(pool, rfp_id):
        raise HTTPException(404, "bid_id not found for this rfp_id")

    client = get_client()
    packet_i_files = get_bid_source_files(client, bid_id, packet="I")
    sealed = record["stage2_result"] is None
    packet_ii_files = [] if sealed else get_bid_source_files(client, bid_id, packet="II")

    # filename must exactly match an already-sanitized name Qdrant recorded
    # at ingestion time (pdf_path.name -- no directory component survives
    # that), not a raw, attacker-controlled path -- this check alone stops
    # path traversal, since a crafted "../../etc/passwd" can never equal a
    # real stored source_file. The resolved-path check below is defense in
    # depth on top of that, not the only thing standing between this
    # endpoint and the filesystem.
    if filename not in packet_i_files and filename not in packet_ii_files:
        raise HTTPException(404, "Document not found, or still sealed")

    bid_dir = (BID_DIR / bid_id).resolve()
    path = (bid_dir / filename).resolve()
    if bid_dir != path.parent:
        raise HTTPException(400, "Invalid filename")
    if not path.exists():
        raise HTTPException(404, "File not found on disk")

    return FileResponse(path, media_type="application/pdf", filename=filename)


@router.post("/{rfp_id}/open-financial-bids")
def open_financial_bids(
    rfp_id: str, background_tasks: BackgroundTasks, request: Request,
    buyer_email: str = Depends(get_current_buyer),
):
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
    _require_owner(record["buyer_email"], buyer_email)
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
    buyer_email: str = Depends(get_current_buyer),
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
    _require_owner(record["buyer_email"], buyer_email)

    save_evidence_resolution(pool, bid_id, criterion_id, body.verdict, body.reasoning)

    graph = request.app.state.graph
    state = graph.get_state(_config(rfp_id))
    structured_rfp = StructuredRFP.model_validate(state.values["structured_rfp"])

    evidence = [
        EvidenceItem(criterion_id=e["criterion_id"], bid_id=bid_id, verdict=e["effective_verdict"],
                     reasoning=e["reasoning"], citation=e["citation"], rule_result=e["rule_result"])
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
def run_l1_selection_endpoint(
    rfp_id: str, body: RunL1SelectionRequest, request: Request,
    buyer_email: str = Depends(get_current_buyer),
):
    """Mirrors GeM's own buyer-triggered "Run L1 selection" feature -- only
    meaningful once Stage 2 found a genuine price tie (see
    backend/scoring/scoring.py's run_l1_selection() for the real mechanism
    this wraps)."""
    pool = request.app.state.db_pool
    record = get_rfp_record(pool, rfp_id)
    if record is None:
        raise HTTPException(404, "rfp_id not found")
    _require_owner(record["buyer_email"], buyer_email)
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
