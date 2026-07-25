"""
LangGraph state -- what flows through the graph and gets persisted at Checkpoint A.

structured_rfp is stored as a plain dict, not a live StructuredRFP object --
LangGraph's Postgres checkpointer serializes state with msgpack, which
doesn't natively know our custom Pydantic types (warned it will start
rejecting them outright in a future version). Each node converts dict <->
StructuredRFP at its own boundary instead of trusting msgpack with the model.
"""
from typing import Literal, TypedDict


class EvaluationState(TypedDict):
    rfp_id: str
    pdf_path: str
    structured_rfp: dict | None  # StructuredRFP.model_dump() -- see module docstring
    status: Literal[
        "extracting", "checking_compliance", "checking_prohibited_practices",
        "awaiting_checkpoint_a", "approved",
    ]
    max_criteria: int | None  # testing-only cap on how many criteria to process; None = no limit
