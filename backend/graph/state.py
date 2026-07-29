"""
LangGraph state -- what flows through the graph and gets persisted at Checkpoint A.

structured_rfp is stored as a plain dict, not a live StructuredRFP object --
LangGraph's Postgres checkpointer serializes state with msgpack, which
doesn't natively know our custom Pydantic types (warned it will start
rejecting them outright in a future version). Each node converts dict <->
StructuredRFP at its own boundary instead of trusting msgpack with the model.
"""
from typing import Literal, NotRequired, TypedDict


class EvaluationState(TypedDict):
    rfp_id: str
    pdf_path: str
    structured_rfp: dict | None  # StructuredRFP.model_dump() -- see module docstring
    status: Literal[
        "extracting", "checking_compliance", "checking_prohibited_practices",
        "awaiting_checkpoint_a", "approved", "failed",
    ]
    max_criteria: int | None  # testing-only cap on how many criteria to process; None = no limit
    # Only set when status == "failed" -- a node raised mid-run and
    # _run_to_checkpoint_a (backend/api/rfp.py) wrote this as the terminal
    # state instead of leaving the last-successful-node status hanging.
    error: NotRequired[str]
    # Who uploaded this RFP -- set once at /rfp/upload time, checked by
    # every pre-publish endpoint (status/criteria/approve) so a different
    # buyer can't view or approve someone else's still-in-review upload.
    # NotRequired so an RFP already mid-flight before this field existed
    # doesn't break -- see _require_owner()'s permissive handling of a
    # missing value in backend/api/rfp.py.
    buyer_email: NotRequired[str]
