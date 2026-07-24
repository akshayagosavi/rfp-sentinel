"""
M13 (partial): wires extract_rfp_criteria -> check_rfp_compliance ->
check_prohibited_practices -> checkpoint_a into a LangGraph graph with
Postgres-backed interrupt/resume.

Deliberately partial, scoped under time pressure to get RFP upload through
Checkpoint A working end-to-end today. Bid evaluation (ingest_bids onward,
M10+) gets added to this same graph in a later session -- not a rewrite,
just more nodes and edges appended after checkpoint_a.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt
from psycopg_pool import ConnectionPool

from backend.graph.check_prohibited_practices import check_prohibited_practices
from backend.graph.check_rfp_compliance import check_rfp_compliance
from backend.graph.extract_rfp_criteria import extract_rfp_criteria
from backend.graph.state import EvaluationState
from backend.models.rfp import StructuredRFP

load_dotenv()

POSTGRES_URL = os.getenv(
    "POSTGRES_URL", "postgresql://rfp_sentinel:rfp_sentinel@localhost:5432/rfp_sentinel"
)


def _extract_node(state: EvaluationState) -> dict:
    rfp = extract_rfp_criteria(Path(state["pdf_path"]), rfp_id=state["rfp_id"])
    max_criteria = state.get("max_criteria")
    if max_criteria is not None:
        rfp.criteria = rfp.criteria[:max_criteria]
    return {"structured_rfp": rfp.model_dump(), "status": "checking_compliance"}


def _compliance_node(state: EvaluationState) -> dict:
    rfp = StructuredRFP.model_validate(state["structured_rfp"])
    rfp = check_rfp_compliance(rfp)
    return {"structured_rfp": rfp.model_dump(), "status": "checking_prohibited_practices"}


def _prohibited_practices_node(state: EvaluationState) -> dict:
    rfp = StructuredRFP.model_validate(state["structured_rfp"])
    rfp = check_prohibited_practices(rfp)
    return {"structured_rfp": rfp.model_dump(), "status": "awaiting_checkpoint_a"}


def _checkpoint_a_node(state: EvaluationState) -> dict:
    approved_criteria = interrupt({
        "type": "checkpoint_a",
        "criteria": state["structured_rfp"]["criteria"],
    })
    rfp_dict = state["structured_rfp"]
    rfp_dict["criteria"] = approved_criteria
    return {"structured_rfp": rfp_dict, "status": "approved"}


def build_graph(checkpointer):
    graph = StateGraph(EvaluationState)
    graph.add_node("extract_rfp_criteria", _extract_node)
    graph.add_node("check_rfp_compliance", _compliance_node)
    graph.add_node("check_prohibited_practices", _prohibited_practices_node)
    graph.add_node("checkpoint_a", _checkpoint_a_node)

    graph.set_entry_point("extract_rfp_criteria")
    graph.add_edge("extract_rfp_criteria", "check_rfp_compliance")
    graph.add_edge("check_rfp_compliance", "check_prohibited_practices")
    graph.add_edge("check_prohibited_practices", "checkpoint_a")
    graph.add_edge("checkpoint_a", END)

    return graph.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.types import Command

    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "data/rfps/Gem Bid Document.pdf"
    n_criteria = int(sys.argv[2]) if len(sys.argv) > 2 else 3  # keep it fast for this smoke test

    with ConnectionPool(POSTGRES_URL, kwargs={"autocommit": True}) as pool:
        checkpointer = PostgresSaver(pool)
        checkpointer.setup()

        graph = build_graph(checkpointer)
        config = {"configurable": {"thread_id": "smoke-test-2"}}

        initial_state: EvaluationState = {
            "rfp_id": "smoke-test-2",
            "pdf_path": pdf_path,
            "structured_rfp": None,
            "status": "extracting",
            "max_criteria": n_criteria,
        }

        print("Invoking graph...", flush=True)
        result = graph.invoke(initial_state, config)

        pending = graph.get_state(config).next
        print(f"Graph paused. Next node(s): {pending}", flush=True)
        assert pending == ("checkpoint_a",), f"expected to pause at checkpoint_a, got {pending}"

        proposed = result["__interrupt__"][0].value["criteria"]
        print(f"Checkpoint A received {len(proposed)} proposed criteria.", flush=True)
        assert len(proposed) == n_criteria, f"expected {n_criteria} criteria, got {len(proposed)} -- the limit didn't apply"

        # Simulate the buyer approving everything unedited.
        result = graph.invoke(Command(resume=proposed), config)

        pending_after = graph.get_state(config).next
        print(f"After resume, next node(s): {pending_after} (empty tuple means the graph finished)", flush=True)
        assert pending_after == (), "graph should have completed after checkpoint_a"

        final_state = graph.get_state(config).values
        print(f"Final status: {final_state['status']}", flush=True)
        print(f"Approved criteria count: {len(final_state['structured_rfp']['criteria'])}", flush=True)
        print("\nGraph paused and resumed correctly, backed by Postgres.", flush=True)
