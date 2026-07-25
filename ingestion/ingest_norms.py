"""
M6: the "main file" for norm ingestion. Automates what M3-M5 proved works
step by step: extract -> filter -> chunk -> embed -> save, for every document
listed in data/norms/manifest.json.

Run for one document (this milestone's scope):
    python -m ingestion.ingest_norms "GeM-GTC-40-1741175351.pdf"

Run for every document in the manifest (M7's scope):
    python -m ingestion.ingest_norms
"""
import json
import re
import sys
from pathlib import Path

from backend.rag.embeddings import embed_texts_safely
from backend.rag.qdrant_client import ensure_norms_collection, get_client, upsert_chunks
from ingestion.chunker import chunk_document
from ingestion.extract_tables import extract_tables_by_page
from ingestion.extract_text import PageText, extract_text_by_page
from ingestion.language_filter import filter_english

NORMS_DIR = Path(__file__).resolve().parent.parent / "data" / "norms"
MANIFEST_PATH = NORMS_DIR / "manifest.json"


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def doc_id_for(entry: dict) -> str:
    version = entry.get("version") or "unversioned"
    return f"{_slugify(entry['norm_name'])}_{version}"


def ingest_document(client, entry: dict) -> int:
    """Runs the full pipeline for one manifest entry. Returns chunk count."""
    pdf_path = NORMS_DIR / entry["filename"]
    page_range = tuple(entry["page_range"]) if entry.get("page_range") else None

    pages = extract_text_by_page(
        pdf_path, use_text_flow=entry.get("use_text_flow", False), page_range=page_range
    )
    pages = [PageText(p.page_number, filter_english(p.text)) for p in pages]
    tables = extract_tables_by_page(pdf_path, page_range=page_range)

    chunks = chunk_document(pages, tables)
    kept_indices, vectors = embed_texts_safely([c.text for c in chunks])
    chunks = [chunks[i] for i in kept_indices]

    doc_metadata = {
        "source_file": entry["filename"],
        "norm_name": entry["norm_name"],
        "status": entry["status"],
        "version": entry.get("version"),
        "effective_date": entry.get("effective_date"),
        "language": "en",
    }

    upsert_chunks(client, doc_id_for(entry), chunks, vectors, doc_metadata)
    return len(chunks)


if __name__ == "__main__":
    manifest = json.loads(MANIFEST_PATH.read_text())
    client = get_client()
    ensure_norms_collection(client)

    target_filename = sys.argv[1] if len(sys.argv) > 1 else None
    entries = manifest["documents"]
    if target_filename:
        entries = [e for e in entries if e["filename"] == target_filename]
        if not entries:
            print(f"No manifest entry for '{target_filename}'")
            sys.exit(1)

    for entry in entries:
        count = ingest_document(client, entry)
        print(f"{entry['filename']}: {count} chunks -> doc_id={doc_id_for(entry)!r}, status={entry['status']!r}")
