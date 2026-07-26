"""
Minimal FastAPI layer for the RFP Sentinel demo.

Run from the repo root (so the `ingestion` package import resolves):
    uvicorn backend.api.main:app --reload --port 8000

Two endpoints, both real end-to-end (upload -> pdfplumber extraction ->
language filter -> section-aware chunking) with a placeholder rule-based
check standing in for the not-yet-built LangGraph/RAG agent layer
(see compliance_rules.py docstring):

  POST /api/rfp/check      - single RFP PDF -> norm-compliance issues
  POST /api/bid/evaluate   - RFP PDF + bid PDF -> bid responsiveness issues
"""
import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from ingestion.extract_text import extract_text_by_page
from ingestion.extract_tables import extract_tables_by_page
from ingestion.language_filter import filter_english
from ingestion.chunker import chunk_document, Chunk

from backend.api.compliance_rules import (
    check_rfp_against_rules,
    evaluate_bid_against_rfp,
    issue_to_dict,
)

app = FastAPI(title="RFP Sentinel API (demo)")

# Wide open for the local demo. Tighten to your actual frontend origin
# before this goes anywhere near a real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _process_pdf(path: Path) -> list[Chunk]:
    pages = extract_text_by_page(path)
    for p in pages:
        p.text = filter_english(p.text)
    tables = extract_tables_by_page(path)
    return chunk_document(pages, tables)


async def _save_upload(upload: UploadFile) -> Path:
    if upload.content_type not in ("application/pdf", "application/octet-stream") \
            and not upload.filename.lower().endswith(".pdf"):
        raise HTTPException(400, f"Expected a PDF, got {upload.filename!r}")
    suffix = Path(upload.filename).suffix or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(await upload.read())
    tmp.close()
    return Path(tmp.name)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/rfp/check")
async def rfp_check(file: UploadFile = File(...)):
    """Buyer/evaluator flow: upload a draft RFP, get back norm-compliance issues."""
    path = await _save_upload(file)
    try:
        chunks = _process_pdf(path)
        issues = check_rfp_against_rules(chunks)
        return {
            "filename": file.filename,
            "pages_processed": max((c.page_number for c in chunks), default=0),
            "chunks_extracted": len(chunks),
            "issues": [issue_to_dict(i) for i in issues],
        }
    finally:
        path.unlink(missing_ok=True)


@app.post("/api/bid/evaluate")
async def bid_evaluate(rfp_file: UploadFile = File(...), bid_file: UploadFile = File(...)):
    """Evaluator flow: upload the RFP plus a bidder's response, get back
    which RFP clauses the bid appears to address."""
    rfp_path = await _save_upload(rfp_file)
    bid_path = await _save_upload(bid_file)
    try:
        rfp_chunks = _process_pdf(rfp_path)
        bid_chunks = _process_pdf(bid_path)
        issues = evaluate_bid_against_rfp(rfp_chunks, bid_chunks)
        return {
            "rfp_filename": rfp_file.filename,
            "bid_filename": bid_file.filename,
            "clauses_checked": len(issues),
            "issues": [issue_to_dict(i) for i in issues],
        }
    finally:
        rfp_path.unlink(missing_ok=True)
        bid_path.unlink(missing_ok=True)
