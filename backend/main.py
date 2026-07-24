"""
FastAPI app -- compiles the graph once at startup, keeps the Postgres
connection pool open for the app's lifetime.

v1 shortcut, done under time pressure: no separate `rfps` metadata table
yet -- FastAPI reads/writes evaluation state directly via the LangGraph
checkpointer, keyed by rfp_id as the thread_id. A real `rfps` table (per
the plan's Postgres Schema section) is still the intended design for
tracking business data across many RFPs long-term -- this is a working
placeholder for a single-RFP demo, flagged here, not hidden.
"""
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from backend.auth import get_current_bidder, get_current_buyer
from backend.graph.build_graph import build_graph

load_dotenv()

POSTGRES_URL = os.getenv(
    "POSTGRES_URL", "postgresql://rfp_sentinel:rfp_sentinel@localhost:5432/rfp_sentinel"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = ConnectionPool(POSTGRES_URL, kwargs={"autocommit": True}, open=True)
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    app.state.graph = build_graph(checkpointer)
    yield
    pool.close()


app = FastAPI(title="RFP Sentinel", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Matches the frontend dev server on any host (localhost, 127.0.0.1, or a
    # LAN IP for a teammate on the same network), not just localhost --
    # needed alongside vite.config.js's server.host and the dynamic API base
    # URL in frontend/src/api/client.js for cross-machine access to work.
    allow_origin_regex=r"http://.*:5173",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


from backend.api.auth import router as auth_router  # noqa: E402
from backend.api.bidder import router as bidder_router  # noqa: E402
from backend.api.rfp import router as rfp_router  # noqa: E402

app.include_router(auth_router)
app.include_router(rfp_router, dependencies=[Depends(get_current_buyer)])
app.include_router(bidder_router, dependencies=[Depends(get_current_bidder)])
