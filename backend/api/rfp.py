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

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile
from langgraph.types import Command
from pydantic import BaseModel

router = APIRouter(prefix="/rfp", tags=["rfp"])

RFP_DIR = Path("data/rfps")


def _config(rfp_id: str) -> dict:
    return {"configurable": {"thread_id": rfp_id}}


def _run_to_checkpoint_a(graph, initial_state: dict, config: dict) -> None:
    graph.invoke(initial_state, config)


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
    return {"rfp_id": rfp_id, "status": state.values.get("status", "unknown")}


@router.get("/{rfp_id}/criteria")
def get_criteria(rfp_id: str, request: Request):
    state = request.app.state.graph.get_state(_config(rfp_id))
    if not state.values or not state.values.get("structured_rfp"):
        raise HTTPException(404, "rfp_id not found, or criteria not ready yet")
    return {"rfp_id": rfp_id, "criteria": state.values["structured_rfp"]["criteria"]}


class ApproveRequest(BaseModel):
    criteria: list[dict]


@router.post("/{rfp_id}/criteria/approve")
def approve_criteria(rfp_id: str, body: ApproveRequest, request: Request):
    graph = request.app.state.graph
    config = _config(rfp_id)
    pending = graph.get_state(config).next
    if pending != ("checkpoint_a",):
        raise HTTPException(409, f"rfp_id is not awaiting Checkpoint A (next node(s): {pending})")
    graph.invoke(Command(resume=body.criteria), config)
    return {"rfp_id": rfp_id, "status": "approved"}
