"""
FastAPI app -- compiles the graph once at startup, keeps the Postgres
connection pool open for the app's lifetime. The same pool backs both
LangGraph's checkpointer (evaluation state) and the real users/rfps/bids
metadata tables in db.py -- one pool, two different uses of Postgres, not
two separate connections to manage.
"""
import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from backend.auth import get_current_admin, get_current_bidder, get_current_buyer
from backend.db import close_rfp, list_due_rfp_ids, seed_demo_users, setup_tables
from backend.graph.build_graph import build_graph
from backend.graph.run_stage1_evaluation import run_stage1_evaluation
from backend.logging_config import get_logger
from backend.models.rfp import StructuredRFP

load_dotenv()

logger = get_logger(__name__)

POSTGRES_URL = os.getenv(
    "POSTGRES_URL", "postgresql://rfp_sentinel:rfp_sentinel@localhost:5432/rfp_sentinel"
)

CLOSING_TIMER_INTERVAL_SECONDS = 60


async def _closing_timer_loop(app: FastAPI) -> None:
    """Polls for published RFPs whose closing_date has passed and closes +
    evaluates them automatically -- the "real" path (a buyer's own manual
    Close & Evaluate Now override, see backend/api/rfp.py, is the demo
    shortcut for not waiting out the real multi-day bid period). A plain
    polling loop, not a cron job/task queue -- there's no other background
    worker in this stack yet, and a 60s-granularity poll is more than
    precise enough against a multi-day closing_date."""
    while True:
        await asyncio.sleep(CLOSING_TIMER_INTERVAL_SECONDS)
        try:
            for rfp_id in list_due_rfp_ids(app.state.db_pool):
                if not close_rfp(app.state.db_pool, rfp_id):
                    continue  # already closed by a concurrent manual override
                state = app.state.graph.get_state({"configurable": {"thread_id": rfp_id}})
                if not state.values or not state.values.get("structured_rfp"):
                    continue
                structured_rfp = StructuredRFP.model_validate(state.values["structured_rfp"])
                logger.info("closing timer: rfp_id=%r past closing_date, evaluating", rfp_id)
                await asyncio.to_thread(run_stage1_evaluation, app.state.db_pool, rfp_id, structured_rfp)
        except Exception:
            logger.exception("closing timer loop iteration failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = ConnectionPool(POSTGRES_URL, kwargs={"autocommit": True}, open=True)
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    setup_tables(pool)
    seed_demo_users(pool)
    app.state.db_pool = pool
    app.state.graph = build_graph(checkpointer)
    timer_task = asyncio.create_task(_closing_timer_loop(app))
    yield
    timer_task.cancel()
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


from backend.api.admin import router as admin_router  # noqa: E402
from backend.api.auth import router as auth_router  # noqa: E402
from backend.api.bidder import router as bidder_router  # noqa: E402
from backend.api.bids import router as bids_router  # noqa: E402
from backend.api.rfp import router as rfp_router  # noqa: E402

app.include_router(auth_router)
app.include_router(bids_router)  # public -- no auth dependency, browsing is open
app.include_router(rfp_router, dependencies=[Depends(get_current_buyer)])
app.include_router(bidder_router, dependencies=[Depends(get_current_bidder)])
app.include_router(admin_router, dependencies=[Depends(get_current_admin)])
