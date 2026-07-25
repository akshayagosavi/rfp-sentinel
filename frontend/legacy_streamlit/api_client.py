"""
Thin wrapper around the FastAPI backend -- Streamlit never talks to
Postgres/LangGraph directly, only through these HTTP calls.
"""
import requests

BASE_URL = "http://127.0.0.1:8000"


def upload_rfp(file_bytes: bytes, filename: str, max_criteria: int | None = None) -> dict:
    params = {"max_criteria": max_criteria} if max_criteria is not None else {}
    resp = requests.post(
        f"{BASE_URL}/rfp/upload",
        params=params,
        files={"file": (filename, file_bytes, "application/pdf")},
    )
    resp.raise_for_status()
    return resp.json()


def get_status(rfp_id: str) -> dict:
    resp = requests.get(f"{BASE_URL}/rfp/{rfp_id}/status")
    resp.raise_for_status()
    return resp.json()


def get_criteria(rfp_id: str) -> dict:
    resp = requests.get(f"{BASE_URL}/rfp/{rfp_id}/criteria")
    resp.raise_for_status()
    return resp.json()


def approve_criteria(rfp_id: str, criteria: list[dict]) -> dict:
    resp = requests.post(f"{BASE_URL}/rfp/{rfp_id}/criteria/approve", json={"criteria": criteria})
    resp.raise_for_status()
    return resp.json()
