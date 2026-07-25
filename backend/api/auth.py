"""
POST /auth/login -- real DB-backed credential check now (see backend/db.py,
backend/auth.py). POST /auth/signup -- bidder self-signup, deliberately
simple: no verification the seller is actually GeM-registered, just a
free-text "proof" field stored for later, real GeM identity integration.

MSE/MII certificates live here (on the account/profile), not on bid
submission -- both are seller-level attributes on real GeM (verified once
against a seller's registration, not re-declared per bid), so asking again
on every submission would just be redundant with what's already on file.
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel

from backend.auth import authenticate_user, create_access_token, create_bidder, get_current_user_email
from backend.db import change_user_password, get_user_profile, update_mii_certificate, update_mse_certificate, update_user_profile

router = APIRouter(prefix="/auth", tags=["auth"])

CERT_DIR = Path("data/certificates")


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: LoginRequest, request: Request):
    user = authenticate_user(request.app.state.db_pool, body.email, body.password)
    if user is None:
        raise HTTPException(401, "Invalid email or password")
    if not user["is_active"]:
        raise HTTPException(403, "This account has been deactivated")
    token = create_access_token(body.email, user["role"])
    return {"access_token": token, "token_type": "bearer", "role": user["role"]}


class BidderSignupRequest(BaseModel):
    email: str
    password: str
    org_name: str
    gem_seller_proof: str | None = None


@router.post("/signup/bidder")
def signup_bidder(body: BidderSignupRequest, request: Request):
    try:
        create_bidder(
            request.app.state.db_pool, body.email, body.password, body.org_name, body.gem_seller_proof
        )
    except ValueError as e:
        raise HTTPException(409, str(e))
    token = create_access_token(body.email, "bidder")
    return {"access_token": token, "token_type": "bearer", "role": "bidder"}


@router.get("/me")
def get_me(request: Request, email: str = Depends(get_current_user_email)):
    profile = get_user_profile(request.app.state.db_pool, email)
    if profile is None:
        raise HTTPException(404, "User not found")
    return profile


class UpdateProfileRequest(BaseModel):
    org_name: str
    gem_seller_proof: str | None = None


@router.patch("/me")
def update_me(body: UpdateProfileRequest, request: Request, email: str = Depends(get_current_user_email)):
    update_user_profile(request.app.state.db_pool, email, body.org_name, body.gem_seller_proof)
    return get_user_profile(request.app.state.db_pool, email)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/me/change-password")
def change_password(body: ChangePasswordRequest, request: Request, email: str = Depends(get_current_user_email)):
    ok = change_user_password(request.app.state.db_pool, email, body.current_password, body.new_password)
    if not ok:
        raise HTTPException(401, "Current password is incorrect")
    return {"status": "changed"}


async def _save_certificate(file: UploadFile) -> str:
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    (CERT_DIR / filename).write_bytes(await file.read())
    return filename


@router.post("/me/mse-certificate")
async def upload_mse_certificate(
    request: Request, file: UploadFile, email: str = Depends(get_current_user_email)
):
    filename = await _save_certificate(file)
    update_mse_certificate(request.app.state.db_pool, email, filename)
    return get_user_profile(request.app.state.db_pool, email)


@router.post("/me/mii-certificate")
async def upload_mii_certificate(
    request: Request, file: UploadFile, email: str = Depends(get_current_user_email)
):
    filename = await _save_certificate(file)
    update_mii_certificate(request.app.state.db_pool, email, filename)
    return get_user_profile(request.app.state.db_pool, email)
