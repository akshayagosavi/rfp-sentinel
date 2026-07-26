"""
Shared API client for RFP Sentinel Streamlit dashboards.
Every page imports this instead of writing its own requests.post() calls.
When v1.1 auth lands, add the token/session header in _post() ONCE, here.
"""
import requests

API_BASE = "http://127.0.0.1:8000"  # change to your deployed FastAPI URL


class ApiError(Exception):
    pass


def _post(path: str, files: dict, timeout: int = 60) -> dict:
    try:
        resp = requests.post(f"{API_BASE}{path}", files=files, timeout=timeout)
    except requests.exceptions.ConnectionError:
        raise ApiError(
            f"Could not reach the API at {API_BASE}. "
            f"Is `uvicorn backend.api.main:app --port 8000` running?"
        )
    if not resp.ok:
        detail = resp.text
        try:
            detail = resp.json().get("detail", detail)
        except ValueError:
            pass
        raise ApiError(f"{resp.status_code}: {detail}")
    return resp.json()


def check_rfp(file_bytes: bytes, filename: str) -> dict:
    """POST /api/rfp/check — returns pages_processed, chunks_extracted, issues[]."""
    files = {"file": (filename, file_bytes, "application/pdf")}
    return _post("/api/rfp/check", files)


def evaluate_bid(rfp_bytes: bytes, rfp_filename: str, bid_bytes: bytes, bid_filename: str) -> dict:
    """POST /api/bid/evaluate — returns clauses_checked, issues[]."""
    files = {
        "rfp_file": (rfp_filename, rfp_bytes, "application/pdf"),
        "bid_file": (bid_filename, bid_bytes, "application/pdf"),
    }
    return _post("/api/bid/evaluate", files)


def health_check() -> bool:
    try:
        resp = requests.get(f"{API_BASE}/api/health", timeout=3)
        return resp.ok
    except requests.exceptions.ConnectionError:
        return False
