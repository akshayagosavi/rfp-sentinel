"""
Real Postgres metadata tables -- users, rfps, bids. Anticipated in the
original project plan's "Postgres Schema" section and deliberately
deferred (RFP criteria lived only inside LangGraph's checkpoint state);
now genuinely needed for real seller signup, searchable/filterable public
listings, and bid lifecycle status (stage1_passed etc.) that a LangGraph
checkpoint can't be queried for directly.

Deliberately NOT an ORM (SQLModel/SQLAlchemy) -- three small tables with
plain CRUD don't need one, and psycopg (v3) is already a dependency via
langgraph-checkpoint-postgres. Reuses the same ConnectionPool main.py
already opens for the LangGraph checkpointer, not a second pool.
"""
import json
import os
from datetime import datetime, timedelta, timezone

from psycopg_pool import ConnectionPool

# GeM's own Custom Bid flow allows a 10-45 day submission window, buyer's
# choice -- 10 is the minimum, used here as the default since there's no
# UI yet for a buyer to pick their own (see ROADMAP.md). Sourced from
# GeM's public bidding-types documentation, not invented.
DEFAULT_BID_PERIOD_DAYS = 10

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('buyer', 'bidder', 'admin')),
    org_name TEXT NOT NULL,
    gem_seller_proof TEXT,  -- bidder-only; whatever the seller enters, NOT validated against GeM
                            -- yet -- a placeholder for real GeM identity integration later, not a
                            -- security control. See backend/api/auth.py's signup endpoint.
    is_mse BOOLEAN NOT NULL DEFAULT FALSE,        -- seller-level, like real GeM registration --
    mse_certificate_filename TEXT,                -- declared once in Profile, not re-asked per bid.
    is_mii_local BOOLEAN NOT NULL DEFAULT FALSE,  -- Backed by an uploaded certificate (Udyam
    mii_certificate_filename TEXT,                -- Registration / local-content declaration), but
                                                   -- the file's CONTENT isn't verified, same caveat
                                                   -- as gem_seller_proof above.
    is_active BOOLEAN NOT NULL DEFAULT TRUE,  -- admin-controlled account suspension -- blocks login,
                                               -- never deletes anything; their past RFPs/bids stay on
                                               -- record, same non-destructive philosophy as norm status
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rfps (
    rfp_id TEXT PRIMARY KEY,  -- matches the LangGraph thread_id -- this table is queryable
                              -- metadata alongside that checkpoint state, not a replacement for it
    buyer_user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Electronics',
    closing_date TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'closed', 'evaluated')),
    gem_bid_number TEXT,  -- GeM's own official bid reference, e.g. "GEM/2024/B/5735766" -- null if
                          -- this RFP has no real GeM listing yet (a brand-new tender drafted here first)
    closed_at TIMESTAMPTZ,
    stage2_result JSONB,  -- Stage2Result.model_dump() (see scoring.py) -- set once "Open Financial
                          -- Bids" completes; status flips to 'evaluated' at the same time
    summary TEXT,  -- bidder-facing plain-language summary, cached after first generation -- the
                   -- RFP's own content is immutable once published, so regenerating it on every
                   -- page view would just be wasted LLM calls for an identical answer
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bids (
    bid_id TEXT PRIMARY KEY,
    rfp_id TEXT NOT NULL REFERENCES rfps(rfp_id),
    bidder_user_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'submitted'
        CHECK (status IN ('submitted', 'under_evaluation', 'stage1_passed', 'stage1_failed')),
    price NUMERIC,          -- NOT collected at submission -- the bidder uploads a financial/price
                            -- document instead (Packet-II, sealed); the actual number only gets
                            -- read once Packet-II is opened during Stage 2 evaluation, not before.
    is_mse BOOLEAN NOT NULL DEFAULT FALSE,       -- snapshotted from the bidder's profile at
    is_mii_local BOOLEAN NOT NULL DEFAULT FALSE, -- submission time, not re-asked per bid (see users table)
    technical_score NUMERIC,          -- Stage 1 output, 0-100 -- see scoring.score_stage1
    failed_criteria JSONB NOT NULL DEFAULT '[]'::jsonb,   -- mandatory criterion_ids that failed
    pending_criteria JSONB NOT NULL DEFAULT '[]'::jsonb,  -- mandatory criterion_ids still awaiting review (not_found)
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    evaluated_at TIMESTAMPTZ
);

-- One row per (bid, criterion) Stage 1 verdict -- the full evidence trail
-- behind a bid's technical_score/failed_criteria, kept separately rather
-- than stuffed into bids since it's one-to-many and Checkpoint B's
-- per-criterion breakdown view (not yet built) will read straight from
-- this table.
CREATE TABLE IF NOT EXISTS bid_evidence (
    id SERIAL PRIMARY KEY,
    bid_id TEXT NOT NULL REFERENCES bids(bid_id),
    criterion_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    reasoning TEXT,
    citation JSONB,
    resolved_verdict TEXT,       -- buyer's human override for a 'not_found' mandatory criterion --
    resolution_reasoning TEXT,   -- required alongside it, same audit-trail discipline as
    resolved_at TIMESTAMPTZ,     -- Criterion.override_reasoning at Checkpoint A. NULL until resolved;
                                  -- when set, this -- not the original LLM verdict -- decides Stage 1.
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def setup_tables(pool: ConnectionPool) -> None:
    with pool.connection() as conn:
        conn.execute(_SCHEMA)
        # CREATE TABLE IF NOT EXISTS above is a no-op once a table already
        # exists -- these migrate existing tables forward for anyone who had
        # them before these columns were added. Safe to run every startup.
        conn.execute("ALTER TABLE rfps ADD COLUMN IF NOT EXISTS gem_bid_number TEXT")
        conn.execute("ALTER TABLE bids ADD COLUMN IF NOT EXISTS price NUMERIC")
        conn.execute("ALTER TABLE bids ADD COLUMN IF NOT EXISTS is_mse BOOLEAN NOT NULL DEFAULT FALSE")
        conn.execute("ALTER TABLE bids ADD COLUMN IF NOT EXISTS is_mii_local BOOLEAN NOT NULL DEFAULT FALSE")
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_mse BOOLEAN NOT NULL DEFAULT FALSE")
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS mse_certificate_filename TEXT")
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_mii_local BOOLEAN NOT NULL DEFAULT FALSE")
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS mii_certificate_filename TEXT")
        conn.execute("ALTER TABLE rfps ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ")
        conn.execute("ALTER TABLE rfps ADD COLUMN IF NOT EXISTS stage2_result JSONB")
        conn.execute("ALTER TABLE bids ADD COLUMN IF NOT EXISTS technical_score NUMERIC")
        conn.execute("ALTER TABLE bids ADD COLUMN IF NOT EXISTS failed_criteria JSONB NOT NULL DEFAULT '[]'::jsonb")
        conn.execute("ALTER TABLE bids ADD COLUMN IF NOT EXISTS pending_criteria JSONB NOT NULL DEFAULT '[]'::jsonb")
        conn.execute("ALTER TABLE bid_evidence ADD COLUMN IF NOT EXISTS resolved_verdict TEXT")
        conn.execute("ALTER TABLE bid_evidence ADD COLUMN IF NOT EXISTS resolution_reasoning TEXT")
        conn.execute("ALTER TABLE bid_evidence ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ")
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE")
        conn.execute("ALTER TABLE rfps ADD COLUMN IF NOT EXISTS summary TEXT")
        # One bid per bidder per RFP for now -- no amend/resubmit flow yet
        # (tracked in ROADMAP.md), so this is a hard constraint, not just a
        # UI convention.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS bids_rfp_bidder_unique ON bids(rfp_id, bidder_user_id)"
        )


def seed_demo_users(pool: ConnectionPool) -> None:
    """Seeds one demo buyer account and one demo admin account, matching
    BUYER_EMAIL/BUYER_PASSWORD and ADMIN_EMAIL/ADMIN_PASSWORD env vars --
    same reasoning as the buyer account (a credential documented in the
    README that keeps working now that login is DB-backed). Admin has no
    self-signup (unlike bidders) -- an admin account is provisioned, not
    created by whoever asks. Idempotent -- safe to call on every startup."""
    from backend.auth import hash_password

    buyer_email = os.getenv("BUYER_EMAIL", "buyer@rfpsentinel.local")
    buyer_password = os.getenv("BUYER_PASSWORD", "changeme")
    admin_email = os.getenv("ADMIN_EMAIL", "admin@rfpsentinel.local")
    admin_password = os.getenv("ADMIN_PASSWORD", "changeme")
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO users (email, password_hash, role, org_name)
            VALUES (%s, %s, 'buyer', 'Demo Buyer Org')
            ON CONFLICT (email) DO NOTHING
            """,
            (buyer_email, hash_password(buyer_password)),
        )
        conn.execute(
            """
            INSERT INTO users (email, password_hash, role, org_name)
            VALUES (%s, %s, 'admin', 'RFP Sentinel Admin')
            ON CONFLICT (email) DO NOTHING
            """,
            (admin_email, hash_password(admin_password)),
        )


def publish_rfp(
    pool: ConnectionPool, rfp_id: str, buyer_email: str, title: str, category: str,
    gem_bid_number: str | None = None, closing_days: int = DEFAULT_BID_PERIOD_DAYS,
) -> None:
    """Called once, right when Checkpoint A is approved -- the real
    'publish' moment. ON CONFLICT DO NOTHING makes this safe to call even
    if somehow invoked twice for the same rfp_id (the graph's own 409
    check already prevents that in practice, this is just a second
    layer)."""
    closing_date = datetime.now(timezone.utc) + timedelta(days=closing_days)
    with pool.connection() as conn:
        buyer_row = conn.execute("SELECT id FROM users WHERE email = %s", (buyer_email,)).fetchone()
        if buyer_row is None:
            raise ValueError(f"No user record for buyer {buyer_email!r}")
        conn.execute(
            """
            INSERT INTO rfps (rfp_id, buyer_user_id, title, category, closing_date, status, gem_bid_number)
            VALUES (%s, %s, %s, %s, %s, 'published', %s)
            ON CONFLICT (rfp_id) DO NOTHING
            """,
            (rfp_id, buyer_row[0], title, category, closing_date, gem_bid_number),
        )


def list_published_rfps(
    pool: ConnectionPool, keyword: str | None = None, category: str | None = None, status: str | None = None,
) -> list[dict]:
    query = """
        SELECT r.rfp_id, r.title, r.category, r.closing_date, r.status, u.org_name AS buyer_org, r.gem_bid_number
        FROM rfps r JOIN users u ON u.id = r.buyer_user_id
        WHERE r.status != 'draft'
    """
    params: list = []
    if keyword:
        # Matches title text OR the real GeM bid number -- a bidder
        # searching "GEM/2024/B/5735766" should find it, same as searching
        # by the tender's title.
        query += " AND (r.title ILIKE %s OR r.gem_bid_number ILIKE %s)"
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    if category:
        query += " AND r.category = %s"
        params.append(category)
    if status:
        query += " AND r.status = %s"
        params.append(status)
    query += " ORDER BY r.created_at DESC"

    with pool.connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        {"rfp_id": r[0], "title": r[1], "category": r[2], "closing_date": r[3].isoformat(),
         "status": r[4], "buyer_org": r[5], "gem_bid_number": r[6]}
        for r in rows
    ]


def get_rfp_record(pool: ConnectionPool, rfp_id: str) -> dict | None:
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT r.rfp_id, r.title, r.category, r.closing_date, r.status, u.org_name AS buyer_org,
                   r.gem_bid_number, r.stage2_result, r.summary
            FROM rfps r JOIN users u ON u.id = r.buyer_user_id
            WHERE r.rfp_id = %s
            """,
            (rfp_id,),
        ).fetchone()
    if row is None:
        return None
    return {"rfp_id": row[0], "title": row[1], "category": row[2], "closing_date": row[3].isoformat(),
            "status": row[4], "buyer_org": row[5], "gem_bid_number": row[6], "stage2_result": row[7],
            "summary": row[8]}


def save_rfp_summary(pool: ConnectionPool, rfp_id: str, summary: str) -> None:
    with pool.connection() as conn:
        conn.execute("UPDATE rfps SET summary = %s WHERE rfp_id = %s", (summary, rfp_id))


def get_user_profile(pool: ConnectionPool, email: str) -> dict | None:
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT email, role, org_name, gem_seller_proof, created_at,
                   is_mse, mse_certificate_filename, is_mii_local, mii_certificate_filename
            FROM users WHERE email = %s
            """,
            (email,),
        ).fetchone()
    if row is None:
        return None
    return {"email": row[0], "role": row[1], "org_name": row[2], "gem_seller_proof": row[3],
            "created_at": row[4].isoformat(), "is_mse": row[5], "mse_certificate_filename": row[6],
            "is_mii_local": row[7], "mii_certificate_filename": row[8]}


def update_user_profile(pool: ConnectionPool, email: str, org_name: str, gem_seller_proof: str | None) -> None:
    with pool.connection() as conn:
        conn.execute(
            "UPDATE users SET org_name = %s, gem_seller_proof = %s WHERE email = %s",
            (org_name, gem_seller_proof, email),
        )


def update_mse_certificate(pool: ConnectionPool, email: str, filename: str) -> None:
    """Declared once in Profile -- uploading a certificate is what sets
    is_mse=True; there's no separate checkbox to fall out of sync with it."""
    with pool.connection() as conn:
        conn.execute(
            "UPDATE users SET is_mse = TRUE, mse_certificate_filename = %s WHERE email = %s",
            (filename, email),
        )


def update_mii_certificate(pool: ConnectionPool, email: str, filename: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            "UPDATE users SET is_mii_local = TRUE, mii_certificate_filename = %s WHERE email = %s",
            (filename, email),
        )


def change_user_password(pool: ConnectionPool, email: str, current_password: str, new_password: str) -> bool:
    """Returns False (no change made) if current_password doesn't match --
    caller turns that into a 401/400, this function just reports success."""
    from backend.auth import hash_password, verify_password

    with pool.connection() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE email = %s", (email,)).fetchone()
        if row is None or not verify_password(current_password, row[0]):
            return False
        conn.execute("UPDATE users SET password_hash = %s WHERE email = %s", (hash_password(new_password), email))
    return True


def has_bidder_applied(pool: ConnectionPool, rfp_id: str, bidder_email: str) -> bool:
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM bids b JOIN users u ON u.id = b.bidder_user_id
            WHERE b.rfp_id = %s AND u.email = %s
            """,
            (rfp_id, bidder_email),
        ).fetchone()
    return row is not None


def create_bid_record(pool: ConnectionPool, bid_id: str, rfp_id: str, bidder_email: str) -> None:
    """is_mse/is_mii_local are snapshotted from the bidder's own profile
    (set once in Profile, not re-asked per submission -- see module
    docstring). price is intentionally left null here -- it's read from
    the uploaded financial document only when Packet-II opens at Stage 2,
    not collected as a number at submission time."""
    with pool.connection() as conn:
        bidder_row = conn.execute(
            "SELECT id, is_mse, is_mii_local FROM users WHERE email = %s", (bidder_email,)
        ).fetchone()
        if bidder_row is None:
            raise ValueError(f"No user record for bidder {bidder_email!r}")
        bidder_id, is_mse, is_mii_local = bidder_row
        conn.execute(
            """
            INSERT INTO bids (bid_id, rfp_id, bidder_user_id, is_mse, is_mii_local)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (bid_id, rfp_id, bidder_id, is_mse, is_mii_local),
        )


def list_rfps_by_buyer(pool: ConnectionPool, buyer_email: str) -> list[dict]:
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT r.rfp_id, r.title, r.status, r.closing_date, r.closed_at,
                   (SELECT COUNT(*) FROM bids b WHERE b.rfp_id = r.rfp_id) AS bid_count
            FROM rfps r
            JOIN users u ON u.id = r.buyer_user_id
            WHERE u.email = %s
            ORDER BY r.created_at DESC
            """,
            (buyer_email,),
        ).fetchall()
    return [
        {"rfp_id": r[0], "title": r[1], "status": r[2], "closing_date": r[3].isoformat(),
         "closed_at": r[4].isoformat() if r[4] else None, "bid_count": r[5]}
        for r in rows
    ]


def close_rfp(pool: ConnectionPool, rfp_id: str) -> bool:
    """Flips a published RFP to closed -- no more submissions accepted past
    this point. Returns False (no-op) if it wasn't in 'published' status,
    so a caller can tell "already closed" apart from "just closed now"
    (relevant for the closing-timer loop re-scanning the same overdue
    row more than once before this transaction commits)."""
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE rfps SET status = 'closed', closed_at = now() WHERE rfp_id = %s AND status = 'published' RETURNING rfp_id",
            (rfp_id,),
        ).fetchone()
    return row is not None


def list_due_rfp_ids(pool: ConnectionPool) -> list[str]:
    """Published RFPs whose closing_date has passed -- what the closing
    timer loop polls for."""
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT rfp_id FROM rfps WHERE status = 'published' AND closing_date <= now()"
        ).fetchall()
    return [r[0] for r in rows]


def list_bid_ids_for_rfp(pool: ConnectionPool, rfp_id: str) -> list[str]:
    with pool.connection() as conn:
        rows = conn.execute("SELECT bid_id FROM bids WHERE rfp_id = %s", (rfp_id,)).fetchall()
    return [r[0] for r in rows]


def mark_bid_under_evaluation(pool: ConnectionPool, bid_id: str) -> None:
    with pool.connection() as conn:
        conn.execute("UPDATE bids SET status = 'under_evaluation' WHERE bid_id = %s", (bid_id,))


def save_bid_evidence(pool: ConnectionPool, bid_id: str, evidence: list[dict]) -> None:
    """evidence: list of EvidenceItem.model_dump() dicts. Replaces any prior
    rows for this bid -- re-running evaluation (e.g. after fixing a bug)
    shouldn't leave stale verdicts sitting alongside fresh ones."""
    with pool.connection() as conn:
        conn.execute("DELETE FROM bid_evidence WHERE bid_id = %s", (bid_id,))
        for item in evidence:
            conn.execute(
                """
                INSERT INTO bid_evidence (bid_id, criterion_id, verdict, reasoning, citation)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (bid_id, item["criterion_id"], item["verdict"], item.get("reasoning"),
                 json.dumps(item["citation"]) if item.get("citation") else None),
            )


def get_bid_evidence(pool: ConnectionPool, bid_id: str) -> list[dict]:
    """One row per (bid, criterion) verdict, each carrying an effective_verdict
    -- the buyer's resolved_verdict if this criterion has been resolved,
    else the original LLM verdict. Callers that need to recompute Stage 1
    (see resolve_pending_evidence in backend/api/rfp.py) use effective_verdict,
    not verdict, so a human resolution actually overrides the original call."""
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT criterion_id, verdict, reasoning, citation, resolved_verdict,
                   resolution_reasoning, resolved_at
            FROM bid_evidence WHERE bid_id = %s
            """,
            (bid_id,),
        ).fetchall()
    return [
        {
            "criterion_id": r[0], "verdict": r[1], "reasoning": r[2], "citation": r[3],
            "resolved_verdict": r[4], "resolution_reasoning": r[5],
            "resolved_at": r[6].isoformat() if r[6] else None,
            "effective_verdict": r[4] or r[1],
        }
        for r in rows
    ]


def save_evidence_resolution(pool: ConnectionPool, bid_id: str, criterion_id: str, verdict: str, reasoning: str) -> None:
    """A buyer's human judgment call on a mandatory criterion that came back
    'not_found' -- same audit-trail discipline as Criterion.override_reasoning
    at Checkpoint A (reasoning is required, not optional, and stored
    permanently alongside the decision)."""
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE bid_evidence
            SET resolved_verdict = %s, resolution_reasoning = %s, resolved_at = now()
            WHERE bid_id = %s AND criterion_id = %s
            """,
            (verdict, reasoning, bid_id, criterion_id),
        )


def save_stage1_result(pool: ConnectionPool, bid_id: str, result: dict) -> None:
    """result: Stage1Result.model_dump() dict (see backend/scoring/scoring.py)."""
    status = "stage1_passed" if result["passed"] else "stage1_failed"
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE bids
            SET status = %s, technical_score = %s, failed_criteria = %s::jsonb,
                pending_criteria = %s::jsonb, evaluated_at = now()
            WHERE bid_id = %s
            """,
            (status, result["technical_score"], json.dumps(result["failed_criteria"]),
             json.dumps(result["pending_criteria"]), bid_id),
        )


def get_stage1_results_for_rfp(pool: ConnectionPool, rfp_id: str) -> list[dict]:
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT b.bid_id, u.org_name, b.status, b.technical_score,
                   b.failed_criteria, b.pending_criteria, b.submitted_at, b.evaluated_at,
                   b.is_mse, b.is_mii_local, b.price
            FROM bids b
            JOIN users u ON u.id = b.bidder_user_id
            WHERE b.rfp_id = %s
            ORDER BY b.submitted_at ASC
            """,
            (rfp_id,),
        ).fetchall()
    return [
        {"bid_id": r[0], "bidder_org": r[1], "status": r[2], "technical_score": float(r[3]) if r[3] is not None else None,
         "failed_criteria": r[4], "pending_criteria": r[5], "submitted_at": r[6].isoformat(),
         "evaluated_at": r[7].isoformat() if r[7] else None, "is_mse": r[8], "is_mii_local": r[9],
         "price": float(r[10]) if r[10] is not None else None}
        for r in rows
    ]


def save_bid_price(pool: ConnectionPool, bid_id: str, price: float) -> None:
    with pool.connection() as conn:
        conn.execute("UPDATE bids SET price = %s WHERE bid_id = %s", (price, bid_id))


def save_stage2_result(pool: ConnectionPool, rfp_id: str, result: dict) -> None:
    """result: Stage2Result.model_dump() dict (see backend/scoring/scoring.py),
    possibly with an added l1_winner/l1_selection_mse_preference_active key
    once run_l1_selection() has resolved a tie (see backend/api/rfp.py).
    Flips the RFP to 'evaluated' -- this is the final stage this project's
    evaluation pipeline reaches."""
    with pool.connection() as conn:
        conn.execute(
            "UPDATE rfps SET stage2_result = %s::jsonb, status = 'evaluated' WHERE rfp_id = %s",
            (json.dumps(result), rfp_id),
        )


def list_bidder_bids(pool: ConnectionPool, bidder_email: str) -> list[dict]:
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT b.bid_id, b.rfp_id, r.title, b.status, b.submitted_at
            FROM bids b
            JOIN rfps r ON r.rfp_id = b.rfp_id
            JOIN users u ON u.id = b.bidder_user_id
            WHERE u.email = %s
            ORDER BY b.submitted_at DESC
            """,
            (bidder_email,),
        ).fetchall()
    return [
        {"bid_id": r[0], "rfp_id": r[1], "rfp_title": r[2], "status": r[3], "submitted_at": r[4].isoformat()}
        for r in rows
    ]


def list_all_users(pool: ConnectionPool) -> list[dict]:
    """Admin-only listing -- every registered account, any role. Deliberately
    excludes password_hash from the returned dict, not just from the
    display: no caller of this function should ever need it."""
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, email, role, org_name, is_active, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
    return [
        {"id": r[0], "email": r[1], "role": r[2], "org_name": r[3], "is_active": r[4], "created_at": r[5].isoformat()}
        for r in rows
    ]


def get_user_by_id(pool: ConnectionPool, user_id: int) -> dict | None:
    with pool.connection() as conn:
        row = conn.execute("SELECT id, email, role FROM users WHERE id = %s", (user_id,)).fetchone()
    if row is None:
        return None
    return {"id": row[0], "email": row[1], "role": row[2]}


def set_user_active(pool: ConnectionPool, user_id: int, is_active: bool) -> bool:
    """Suspends/restores login access -- never deletes the account or
    touches anything they've published/submitted (same non-destructive
    philosophy as norm status transitions). Returns False if user_id
    doesn't exist, so the caller can 404 instead of silently no-op'ing."""
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE users SET is_active = %s WHERE id = %s RETURNING id", (is_active, user_id)
        ).fetchone()
    return row is not None


def is_user_active(pool: ConnectionPool, email: str) -> bool:
    """Checked on every authenticated request (backend/auth.py's
    get_current_*), not just at login -- makes a deactivation take effect
    immediately instead of waiting for the user's existing JWT to expire.
    A user that no longer exists is treated as inactive (deny), not an
    error -- same fail-closed default as any other missing-record case."""
    with pool.connection() as conn:
        row = conn.execute("SELECT is_active FROM users WHERE email = %s", (email,)).fetchone()
    return bool(row and row[0])
