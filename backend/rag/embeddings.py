"""
M6: convert chunk text into embedding vectors using nomic-embed-text via
Ollama — this is "the translator": text in, a list of 768 numbers out.
"""
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

# Defensive cap, not a design choice -- real GeM-generated PDFs (wide tables,
# especially) produced chunks up to ~12,800 chars that made Ollama's
# /api/embeddings return a 500, crashing ingestion outright. Every chunk
# that's actually been proven to embed fine so far has stayed well under
# this. This is a last-resort guard against a chunking edge case, not a
# substitute for chunker.py producing reasonably-sized chunks in the first
# place -- if this limit is getting hit often, that's a chunker bug to fix,
# not something to raise the ceiling on.
_MAX_EMBED_CHARS = 6000


def embed_text(text: str) -> list[float]:
    if len(text) > _MAX_EMBED_CHARS:
        text = text[:_MAX_EMBED_CHARS]
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """One call per chunk, sequentially — no GPU here, so keeping memory
    use predictable matters more than the speed a batched call might give."""
    return [embed_text(t) for t in texts]


def embed_texts_safely(texts: list[str]) -> tuple[list[int], list[list[float]]]:
    """Like embed_texts(), but a single bad chunk can never crash the whole
    ingestion run. Real GeM-generated PDFs have shown more than one distinct
    way to produce text Ollama's embedding endpoint 500s on (oversized
    chunks, doubled-rendering artifacts diluted below detection by
    interspersed (cid:N) placeholder noise) -- rather than chase every
    possible variant, this is the general safety net: skip and log whatever
    fails, keep going. Returns which original indices succeeded, so the
    caller can filter any parallel list (e.g. chunk metadata) to match."""
    kept_indices = []
    vectors = []
    for i, text in enumerate(texts):
        try:
            vectors.append(embed_text(text))
            kept_indices.append(i)
        except requests.exceptions.HTTPError as e:
            print(f"embed_texts_safely: skipped a chunk that failed to embed ({len(text)} chars): {e}")
    return kept_indices, vectors


if __name__ == "__main__":
    samples = [
        "The Seller shall offer a minimum discount of 10% on MRP.",
        "Micro and Small Enterprises are eligible for tender exemptions.",
    ]
    vectors = embed_texts(samples)
    for text, vector in zip(samples, vectors):
        print(f"{len(vector)}-dim vector for: {text[:60]!r}")
        print(f"first 5 values: {vector[:5]}\n")
