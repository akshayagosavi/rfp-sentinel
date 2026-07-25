"""
M10: the "main file" for bid ingestion -- mirrors ingest_norms.py's shape.

A bid submission is one bid_id spanning multiple PDF files (technical
proposal, financial bid, EMD proof, etc.). Each file goes through the same
extract -> filter -> chunk -> embed -> save pipeline already proven on
norms and RFPs, then lands in Qdrant's `bids` collection tagged with
bid_id/rfp_id/source_file/packet, so evidence-checking can later search
just this one bidder's content, and only the packet it's allowed to see
(GFR Rule 189 -- Packet-II/financial stays sealed during technical
evaluation), in isolation from every other bidder.

Run:
    python -m ingestion.ingest_bid <rfp_id> <bidder_name> I:tech1.pdf I:tech2.pdf II:financial.pdf
    (each file is prefixed "I:" or "II:" to say which packet it belongs to)
"""
import sys
import uuid
from pathlib import Path

from backend.rag.embeddings import embed_texts_safely
from backend.rag.qdrant_client import ensure_bids_collection, get_client, upsert_bid_chunks
from ingestion.chunker import chunk_document
from ingestion.extract_tables import extract_tables_by_page
from ingestion.extract_text import PageText, extract_text_by_page
from ingestion.language_filter import filter_english


def ingest_bid(
    client, bid_id: str, rfp_id: str, bidder_name: str, files: list[tuple[str, Path]]
) -> int:
    """files is a list of (packet, pdf_path) pairs, packet being "I" or "II".
    Runs the full pipeline for every file in one bid submission. Returns
    total chunk count."""
    total_chunks = 0
    for packet, pdf_path in files:
        pages = extract_text_by_page(pdf_path)
        pages = [PageText(p.page_number, filter_english(p.text)) for p in pages]
        tables = extract_tables_by_page(pdf_path)

        chunks = chunk_document(pages, tables)
        kept_indices, vectors = embed_texts_safely([c.text for c in chunks])
        chunks = [chunks[i] for i in kept_indices]

        upsert_bid_chunks(client, bid_id, rfp_id, bidder_name, pdf_path.name, packet, chunks, vectors)
        total_chunks += len(chunks)

    return total_chunks


def _parse_file_arg(arg: str) -> tuple[str, Path]:
    if ":" not in arg or arg.split(":", 1)[0] not in ("I", "II"):
        raise ValueError(f"Each file must be prefixed 'I:' or 'II:', got {arg!r}")
    packet, path_str = arg.split(":", 1)
    return packet, Path(path_str)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(
            "Usage: python -m ingestion.ingest_bid <rfp_id> <bidder_name> "
            "I:file1.pdf [I:file2.pdf ...] II:file3.pdf [II:file4.pdf ...]"
        )
        sys.exit(1)

    rfp_id = sys.argv[1]
    bidder_name = sys.argv[2]

    try:
        files = [_parse_file_arg(a) for a in sys.argv[3:]]
    except ValueError as e:
        print(e)
        sys.exit(1)

    for _, p in files:
        if not p.exists():
            print(f"File not found: {p}")
            sys.exit(1)

    bid_id = uuid.uuid4().hex[:8]

    client = get_client()
    ensure_bids_collection(client)

    count = ingest_bid(client, bid_id, rfp_id, bidder_name, files)
    n_technical = sum(1 for packet, _ in files if packet == "I")
    n_financial = sum(1 for packet, _ in files if packet == "II")
    print(
        f"bid_id={bid_id!r}: {count} chunks across {len(files)} file(s) "
        f"({n_technical} Packet-I, {n_financial} Packet-II) "
        f"for rfp_id={rfp_id!r}, bidder={bidder_name!r}"
    )
