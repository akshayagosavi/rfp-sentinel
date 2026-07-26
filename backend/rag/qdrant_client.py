"""
M6: Qdrant setup and storage — "the filing cabinet". Creates the `norms`
collection with the right structure, saves chunks into it, and provides a
cheap way to flip a norm's status (active/superseded/withdrawn) without
re-processing its PDF.
"""
import os
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from ingestion.chunker import Chunk

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
NORMS_COLLECTION = "norms"
BIDS_COLLECTION = "bids"
VECTOR_SIZE = 1024  # bge-m3's dense embedding dimension (was 768 for nomic-embed-text)

# Fixed namespace so the same doc_id + chunk_index always produces the same
# point ID — re-running ingestion overwrites existing points instead of
# creating duplicates.
_ID_NAMESPACE = uuid.UUID("a3f1c9d2-4e6b-4a1a-9c3d-8f2b1e6a7c90")


def get_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def ensure_norms_collection(client: QdrantClient) -> None:
    if not client.collection_exists(NORMS_COLLECTION):
        client.create_collection(
            collection_name=NORMS_COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        client.create_payload_index(NORMS_COLLECTION, "status", PayloadSchemaType.KEYWORD)
        client.create_payload_index(NORMS_COLLECTION, "norm_name", PayloadSchemaType.KEYWORD)
        client.create_payload_index(NORMS_COLLECTION, "doc_id", PayloadSchemaType.KEYWORD)


def chunk_point_id(doc_id: str, chunk_index: int) -> str:
    """Deterministic — same inputs always produce the same ID."""
    return str(uuid.uuid5(_ID_NAMESPACE, f"{doc_id}:{chunk_index}"))


def upsert_chunks(
    client: QdrantClient,
    doc_id: str,
    chunks: list[Chunk],
    vectors: list[list[float]],
    doc_metadata: dict,
) -> None:
    """doc_metadata carries the per-document fields that are the same for
    every chunk (source_file, norm_name, status, version, effective_date,
    language) — per-chunk fields (text, page_number, clause_ref, chunk_type)
    come from the chunk itself."""
    points = [
        PointStruct(
            id=chunk_point_id(doc_id, i),
            vector=vector,
            payload={
                "doc_id": doc_id,
                "chunk_type": chunk.chunk_type,
                "page_number": chunk.page_number,
                "clause_ref": chunk.clause_ref,
                "text": chunk.text,
                **doc_metadata,
            },
        )
        for i, (chunk, vector) in enumerate(zip(chunks, vectors))
    ]
    client.upsert(collection_name=NORMS_COLLECTION, points=points)


def mark_status(client: QdrantClient, norm_name: str, new_status: str) -> None:
    """Cheap payload-only update — flips every chunk belonging to a norm to
    a new status (active/superseded/withdrawn) without touching vectors or
    re-reading the PDF. This is the mechanism for 'norm A got disabled.'"""
    client.set_payload(
        collection_name=NORMS_COLLECTION,
        payload={"status": new_status},
        points=Filter(must=[FieldCondition(key="norm_name", match=MatchValue(value=norm_name))]),
    )


def list_norms(client: QdrantClient) -> list[dict]:
    """One row per distinct norm_name (not one per chunk) -- scrolls the
    whole norms collection and dedupes in Python since Qdrant has no native
    GROUP BY. Fine at this scale (a handful of norm documents, hundreds of
    chunks each); revisit with a dedicated summary collection only if that
    stops being true. Backs the admin norm-management UI's status controls
    -- mark_status() itself has existed since M6/M7, this is what finally
    surfaces it."""
    points, _ = client.scroll(
        collection_name=NORMS_COLLECTION,
        limit=10000,
        with_payload=["norm_name", "status", "version", "effective_date", "source_file"],
    )
    by_name: dict[str, dict] = {}
    for p in points:
        payload = p.payload
        name = payload["norm_name"]
        if name not in by_name:
            by_name[name] = {
                "norm_name": name,
                "status": payload["status"],
                "version": payload.get("version"),
                "effective_date": payload.get("effective_date"),
                "source_file": payload.get("source_file"),
                "chunk_count": 0,
            }
        by_name[name]["chunk_count"] += 1
    return sorted(by_name.values(), key=lambda n: n["norm_name"])


def search_active(client: QdrantClient, query_vector: list[float], top_k: int = 5):
    return client.query_points(
        collection_name=NORMS_COLLECTION,
        query=query_vector,
        query_filter=Filter(must=[FieldCondition(key="status", match=MatchValue(value="active"))]),
        limit=top_k,
    ).points


# --- Bids: one bidder's submission (multiple PDFs) -> Qdrant, isolated by
# bid_id. Same pattern as the norms collection above (deterministic IDs,
# status field), just pointed at bid documents instead of government rules.


def ensure_bids_collection(client: QdrantClient) -> None:
    if not client.collection_exists(BIDS_COLLECTION):
        client.create_collection(
            collection_name=BIDS_COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        client.create_payload_index(BIDS_COLLECTION, "bid_id", PayloadSchemaType.KEYWORD)
        client.create_payload_index(BIDS_COLLECTION, "rfp_id", PayloadSchemaType.KEYWORD)
        client.create_payload_index(BIDS_COLLECTION, "status", PayloadSchemaType.KEYWORD)
        client.create_payload_index(BIDS_COLLECTION, "packet", PayloadSchemaType.KEYWORD)


def bid_chunk_point_id(bid_id: str, source_file: str, chunk_index: int) -> str:
    """Deterministic, like chunk_point_id() -- includes source_file since a
    single bid_id spans multiple documents, so chunk_index alone isn't
    unique across them."""
    return str(uuid.uuid5(_ID_NAMESPACE, f"{bid_id}:{source_file}:{chunk_index}"))


def upsert_bid_chunks(
    client: QdrantClient,
    bid_id: str,
    rfp_id: str,
    bidder_name: str,
    source_file: str,
    packet: str,
    chunks: list[Chunk],
    vectors: list[list[float]],
) -> None:
    """packet is "I" (technical) or "II" (financial) -- required, not
    optional, since this is the field the GFR Rule 189 seal depends on. See
    search_bid() for how it's enforced at read time."""
    if packet not in ("I", "II"):
        raise ValueError(f"packet must be 'I' or 'II', got {packet!r}")
    points = [
        PointStruct(
            id=bid_chunk_point_id(bid_id, source_file, i),
            vector=vector,
            payload={
                "bid_id": bid_id,
                "rfp_id": rfp_id,
                "bidder_name": bidder_name,
                "source_file": source_file,
                "packet": packet,
                "chunk_type": chunk.chunk_type,
                "page_number": chunk.page_number,
                "clause_ref": chunk.clause_ref,
                "text": chunk.text,
                "status": "active",
                "closed_at": None,
            },
        )
        for i, (chunk, vector) in enumerate(zip(chunks, vectors))
    ]
    client.upsert(collection_name=BIDS_COLLECTION, points=points)


def search_bid(
    client: QdrantClient, query_vector: list[float], bid_id: str, packet: str = "I", top_k: int = 5
):
    """Every search is filtered to one bid_id (isolation between bidders)
    AND one packet (isolation between technical and financial content).
    packet defaults to "I" deliberately -- GFR Rule 189 requires Packet-II
    (pricing) to stay sealed until technical evaluation concludes, so the
    safe behavior if a caller forgets to specify is to see technical
    content only, never financial. Stage 2 (price ranking, once built)
    will be the only caller that ever passes packet="II" explicitly.
    A closed bid stays searchable too; status only controls the purge
    script (see close_bid), not visibility."""
    if packet not in ("I", "II"):
        raise ValueError(f"packet must be 'I' or 'II', got {packet!r}")
    return client.query_points(
        collection_name=BIDS_COLLECTION,
        query=query_vector,
        query_filter=Filter(must=[
            FieldCondition(key="bid_id", match=MatchValue(value=bid_id)),
            FieldCondition(key="packet", match=MatchValue(value=packet)),
        ]),
        limit=top_k,
    ).points


def get_bid_source_files(client: QdrantClient, bid_id: str, packet: str = "I") -> list[str]:
    """Distinct uploaded filenames for one bid's packet -- used for the
    document-completeness check (did the bidder submit the right document
    TYPES at all), a fast presence check that's separate from and earlier
    than search_bid()'s per-criterion content matching."""
    if packet not in ("I", "II"):
        raise ValueError(f"packet must be 'I' or 'II', got {packet!r}")
    points, _ = client.scroll(
        collection_name=BIDS_COLLECTION,
        scroll_filter=Filter(must=[
            FieldCondition(key="bid_id", match=MatchValue(value=bid_id)),
            FieldCondition(key="packet", match=MatchValue(value=packet)),
        ]),
        limit=1000,
        with_payload=["source_file"],
    )
    return sorted({p.payload["source_file"] for p in points})


def get_bid_packet_text(client: QdrantClient, bid_id: str, packet: str = "II") -> str:
    """Full concatenated text of every chunk in one bid's packet, page-ordered
    -- unlike search_bid()'s semantic top-k search, this is a plain scroll
    (no query vector), for when the caller needs the whole document's
    content at once rather than the most relevant excerpt. Built for Stage
    2 price extraction: a total price figure could be anywhere in a
    price-schedule document, so there's no useful query to search with --
    the whole thing needs to go to the model."""
    if packet not in ("I", "II"):
        raise ValueError(f"packet must be 'I' or 'II', got {packet!r}")
    points, _ = client.scroll(
        collection_name=BIDS_COLLECTION,
        scroll_filter=Filter(must=[
            FieldCondition(key="bid_id", match=MatchValue(value=bid_id)),
            FieldCondition(key="packet", match=MatchValue(value=packet)),
        ]),
        limit=1000,
        with_payload=["text", "page_number"],
    )
    ordered = sorted(points, key=lambda p: p.payload.get("page_number") or 0)
    return "\n\n".join(p.payload["text"] for p in ordered)


def close_bid(client: QdrantClient, bid_id: str) -> None:
    """Soft-delete: marks every chunk for this bid 'closed' with a timestamp,
    once the bidding period ends and a winner is confirmed. A separate purge
    script (not built yet) does the real deletion after the retention window
    -- this just starts the clock."""
    client.set_payload(
        collection_name=BIDS_COLLECTION,
        payload={"status": "closed", "closed_at": datetime.now(timezone.utc).isoformat()},
        points=Filter(must=[FieldCondition(key="bid_id", match=MatchValue(value=bid_id))]),
    )


if __name__ == "__main__":
    client = get_client()
    ensure_norms_collection(client)
    print(f"Collection '{NORMS_COLLECTION}' ready.")
    print(f"Example deterministic ID for ('gem-gtc_4.0', 0): {chunk_point_id('gem-gtc_4.0', 0)}")
    print(f"Same inputs again: {chunk_point_id('gem-gtc_4.0', 0)}")
