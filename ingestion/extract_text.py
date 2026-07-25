"""
M3: extract per-page text from a PDF using pdfplumber.

extract_text_by_page() is the sole seam where an OCR fallback would slot in
later — if a page's extracted text comes back empty (a scanned image page),
that's the trigger point for it, not implemented in v1.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

import pdfplumber


@dataclass
class PageText:
    page_number: int
    text: str


def _looks_doubled(text: str) -> bool:
    """Detects the "fake bold" rendering artifact: a PDF draws each line
    twice for a bold effect, and pdfplumber's default extraction interleaves
    both passes character-by-character, doubling every letter ("NNoo..
    PP--4455.."). Signature: an alphabetic character is immediately followed
    by an identical copy of itself, far more often than normal text would
    ever produce by coincidence (a real double letter like "committee" is
    rare and isolated, not systematic). Checks the whole string, not a
    prefix sample -- a page can have normal text before a doubled section,
    which would dilute a prefix-only ratio below the threshold and miss it."""
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 40:
        return False
    doubled = sum(1 for a, b in zip(letters, letters[1:]) if a == b)
    return doubled / len(letters) > 0.3


def extract_text_by_page(
    pdf_path: Path, use_text_flow: bool = False, page_range: tuple[int, int] | None = None
) -> list[PageText]:
    """use_text_flow=True forces the flow-respecting extraction; left off by
    default, per-page auto-detection (_looks_doubled) retries just the
    affected page with it instead. Confirmed this flag changes extraction
    *order* too (not just fixing doubling) on already-working documents
    (footer/page-number placement shifts) -- that's exactly why this is a
    targeted per-page retry, not a global switch: only pages that actually
    show the doubling signature get re-extracted differently, everything
    else keeps its original, already-verified extraction untouched.

    page_range (1-indexed, inclusive) lets a manifest entry ingest just the
    relevant chapter of a large multi-topic document (e.g. GFR 2017's ~200
    pages cover budgeting/accounts/audit too -- only one ~17-page chapter is
    actually about procurement) without needing a separately trimmed PDF file
    kept in sync with the source."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        start, end = page_range if page_range else (1, len(pdf.pages))
        for i, page in enumerate(pdf.pages, start=1):
            if i < start or i > end:
                continue
            text = page.extract_text(use_text_flow=use_text_flow) or ""
            if not use_text_flow and _looks_doubled(text):
                text = page.extract_text(use_text_flow=True) or ""
            pages.append(PageText(page_number=i, text=text))
    return pages


if __name__ == "__main__":
    path = Path(sys.argv[1])
    for page in extract_text_by_page(path):
        print(f"--- page {page.page_number} ({len(page.text)} chars) ---")
        print(page.text[:500])
        print()
