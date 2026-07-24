"""
Minimal v1 login: hardcoded per-role credentials (env-configured), JWT
issued on success carrying the role. No password hashing, no `users`
table -- a documented shortcut for the demo, not production-grade auth.
Real multi-user credential auth (Postgres `users`, hashed passwords) is
v1.1 scope per the plan; this exists only so each dashboard has a real
login round-trip to show, not a client-side fake.
"""
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "dev-only-secret-change-me")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

BUYER_EMAIL = os.getenv("BUYER_EMAIL", "buyer@rfpsentinel.local")
BUYER_PASSWORD = os.getenv("BUYER_PASSWORD", "changeme")
BIDDER_EMAIL = os.getenv("BIDDER_EMAIL", "bidder@rfpsentinel.local")
BIDDER_PASSWORD = os.getenv("BIDDER_PASSWORD", "changeme")

_bearer = HTTPBearer()


def authenticate(email: str, password: str) -> str | None:
    """Returns the matched role ("buyer"/"bidder"), or None if no
    credential pair matches."""
    if email == BUYER_EMAIL and password == BUYER_PASSWORD:
        return "buyer"
    if email == BIDDER_EMAIL and password == BIDDER_PASSWORD:
        return "bidder"
    return None


def create_access_token(email: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": email, "role": role, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def _decode(creds: HTTPAuthorizationCredentials) -> dict:
    try:
        return jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")


def get_current_buyer(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    payload = _decode(creds)
    if payload.get("role") != "buyer":
        raise HTTPException(403, "Buyer role required")
    return payload["sub"]


def get_current_bidder(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    payload = _decode(creds)
    if payload.get("role") != "bidder":
        raise HTTPException(403, "Bidder role required")
    return payload["sub"]
