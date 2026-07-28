"""
Role-aware login backed by a real Postgres `users` table (see db.py) --
real password hashing (bcrypt), since these are now real accounts a
person creates via signup, not one hardcoded demo credential where
hashing would be theater. JWT still carries the role, same as before;
only how a credential gets verified changed.
"""
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import psycopg
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg_pool import ConnectionPool

SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "dev-only-secret-change-me")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

_bearer = HTTPBearer()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def authenticate_user(pool: ConnectionPool, email: str, password: str) -> dict | None:
    """Returns the user record (id, role, org_name, is_active) on success,
    None on any credential failure -- wrong email and wrong password look
    identical to the caller, standard practice so a login attempt can't be
    used to probe which emails exist. is_active is checked by the caller
    (backend/api/auth.py's login endpoint), not here -- credentials are
    verified first regardless of active status, so a wrong-password guess
    against a deactivated account still reads as "invalid credentials,"
    not "deactivated," avoiding a second way to leak account status."""
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id, password_hash, role, org_name, is_active FROM users WHERE email = %s", (email,)
        ).fetchone()
    if row is None:
        return None
    user_id, password_hash, role, org_name, is_active = row
    if not verify_password(password, password_hash):
        return None
    return {"id": user_id, "role": role, "org_name": org_name, "is_active": is_active}


def create_bidder(pool: ConnectionPool, email: str, password: str, org_name: str, gem_seller_proof: str | None) -> int:
    """Signup is deliberately simple: no verification that gem_seller_proof
    is a real GeM registration -- once this integrates with real GeM seller
    identity, this is the field that check would validate against. For now
    it's stored as-provided, a placeholder, not a security control."""
    with pool.connection() as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO users (email, password_hash, role, org_name, gem_seller_proof)
                VALUES (%s, %s, 'bidder', %s, %s)
                RETURNING id
                """,
                (email, hash_password(password), org_name, gem_seller_proof),
            ).fetchone()
        except psycopg.errors.UniqueViolation:
            raise ValueError("An account with this email already exists")
    return row[0]


def create_buyer(pool: ConnectionPool, email: str, password: str, org_name: str) -> int:
    """Unlike bidders, buyers don't get open self-signup -- a buyer account
    represents an authorized government department publishing real tenders,
    not something anyone should be able to claim by registering. This is
    only ever called from an admin-gated endpoint (backend/api/admin.py),
    same 'provisioned, not self-signed-up' discipline already used for
    admin accounts (see db.py's seed_demo_users)."""
    with pool.connection() as conn:
        try:
            row = conn.execute(
                """
                INSERT INTO users (email, password_hash, role, org_name)
                VALUES (%s, %s, 'buyer', %s)
                RETURNING id
                """,
                (email, hash_password(password), org_name),
            ).fetchone()
        except psycopg.errors.UniqueViolation:
            raise ValueError("An account with this email already exists")
    return row[0]


def create_access_token(email: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": email, "role": role, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def _decode(creds: HTTPAuthorizationCredentials) -> dict:
    try:
        return jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")


def _check_active(request: Request, email: str) -> None:
    """Closes the gap a JWT's own expiry can't: deactivating a user
    (backend/api/admin.py) previously only blocked *new* logins -- an
    already-issued token stayed valid until its 24h expiry regardless.
    This makes deactivation take effect immediately on every subsequent
    authenticated request, not just at the next login attempt. One extra
    indexed lookup per request (users.email is UNIQUE, so this is a
    single-row lookup) -- the same tradeoff ordinary session-based auth
    makes for the same reason, here paid explicitly since JWTs are
    otherwise stateless."""
    from backend.db import is_user_active  # local import: avoids a circular import with db.py

    if not is_user_active(request.app.state.db_pool, email):
        raise HTTPException(403, "This account has been deactivated")


def get_current_buyer(request: Request, creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    payload = _decode(creds)
    if payload.get("role") != "buyer":
        raise HTTPException(403, "Buyer role required")
    email = payload["sub"]
    _check_active(request, email)
    return email


def get_current_bidder(request: Request, creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    payload = _decode(creds)
    if payload.get("role") != "bidder":
        raise HTTPException(403, "Bidder role required")
    email = payload["sub"]
    _check_active(request, email)
    return email


def get_current_admin(request: Request, creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    payload = _decode(creds)
    if payload.get("role") != "admin":
        raise HTTPException(403, "Admin role required")
    email = payload["sub"]
    _check_active(request, email)
    return email


def get_current_user_email(request: Request, creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    """Any authenticated role -- for endpoints like /auth/me that aren't
    role-specific, unlike get_current_buyer/get_current_bidder above."""
    email = _decode(creds)["sub"]
    _check_active(request, email)
    return email
