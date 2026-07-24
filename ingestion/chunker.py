"""
M5: turn extracted (and language-filtered) pages/tables into embeddable chunks.

Chunking strategy: SECTION-AWARE, not fixed-size. A chunk never spans two
different clauses/sections — that's a hard boundary, not a soft nudge. This
matters specifically because two unrelated clauses can both discuss the same
kind of thing (e.g. a discount/exemption) under different rules; a chunk that
blends the tail of one clause with the head of another produces confidently
wrong retrieval, not just a messy chunk.

Steps:
  1. strip_boilerplate — drop running headers/footers (page numbers, repeated
     titles) detected by frequency across the document, not hardcoded per-file.
  2. chunk_prose — split into sections at detected clause/heading boundaries
     (numbered clauses like "1.", "Rule 4", "(a)", OR standalone all-caps
     heading lines). Each section becomes one chunk if it's a reasonable
     size; oversized sections are sub-split by word count *within* that
     section only, never crossing into the next one.
  3. chunk_tables — one chunk per table (never split by size unless very
     large), serialized as pipe-delimited rows so column structure survives.
"""
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ingestion.extract_text import PageText, _looks_doubled, extract_text_by_page
from ingestion.extract_tables import PageTable, extract_tables_by_page

TARGET_WORDS = 1200      # sub-split window size for oversized sections
MAX_SECTION_WORDS = 1500  # sections up to this size stay as a single chunk
OVERLAP_WORDS = 180      # ~15%, applied only within a single oversized section

HEADING_PATTERN = re.compile(
    r"^\s*(Rule\s+\d+[A-Za-z]?\b|Clause\s+\d+(?:\.\d+)*\b|Section\s+\d+\b|"
    r"Order\s+No\.?\s*\S+|\d+\.(?=\s)|\(\d+\)(?=\s)|"
    r"[A-Z]{1,4}\.(?=\s)|[a-z]{1,4}\.(?=\s)|[a-z]\)(?=\s))"
)

_DIGIT_RUN = re.compile(r"\d+")


@dataclass
class Chunk:
    text: str
    chunk_type: str  # "prose" | "table"
    page_number: int
    clause_ref: str | None = None


@dataclass
class _Section:
    clause_ref: str | None
    page_number: int
    lines: list[str] = field(default_factory=list)


def strip_boilerplate(pages: list[PageText]) -> list[PageText]:
    """Drop lines that repeat across most pages (running headers/footers),
    detected by normalizing digit runs so 'Page 1 of 52' and 'Page 2 of 52'
    count as the same recurring line."""
    if len(pages) < 2:
        return pages

    line_counts: dict[str, int] = {}
    for page in pages:
        seen_this_page = set()
        for line in page.text.splitlines():
            norm = _DIGIT_RUN.sub("#", line.strip())
            if norm and norm not in seen_this_page:
                line_counts[norm] = line_counts.get(norm, 0) + 1
                seen_this_page.add(norm)

    threshold = max(2, int(len(pages) * 0.5))
    boilerplate = {norm for norm, count in line_counts.items() if count >= threshold}

    cleaned = []
    for page in pages:
        kept_lines = [
            line for line in page.text.splitlines()
            if _DIGIT_RUN.sub("#", line.strip()) not in boilerplate
        ]
        cleaned.append(PageText(page_number=page.page_number, text="\n".join(kept_lines)))
    return cleaned


def _is_allcaps_heading(line: str) -> bool:
    """Catches standalone heading lines that aren't numbered, e.g. document
    section titles like 'ELECTRONIC GAMES' or 'GENERAL TERMS AND DEFINITIONS'
    — but not incidental all-caps abbreviations sitting inside a normal
    sentence (checked against the *whole* line's letter ratio, so a line
    like 'Marked degree of protection to IEC 60529' won't trigger this)."""
    stripped = line.strip()
    letters = [c for c in stripped if c.isalpha()]
    if len(letters) < 6:
        return False
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    return upper_ratio > 0.85 and len(stripped.split()) >= 2


def _split_into_sections(pages: list[PageText]) -> list[_Section]:
    """Numbered/lettered markers always start a new section. All-caps lines
    only start a new section on the *first* line of a run — consecutive
    all-caps lines (a multi-line title block, e.g. a heading that wraps
    across 3-4 lines) merge into that same section instead of each becoming
    their own one-line fragment."""
    sections: list[_Section] = []
    current: _Section | None = None
    prev_was_allcaps = False

    for page in pages:
        for line in page.text.splitlines():
            if not line.strip():
                continue
            match = HEADING_PATTERN.match(line)
            is_allcaps = _is_allcaps_heading(line)
            starts_new_section = bool(match) or (is_allcaps and not prev_was_allcaps)

            if starts_new_section:
                if current and current.lines:
                    sections.append(current)
                clause_label = match.group(1).strip() if match else line.strip()[:60]
                current = _Section(clause_ref=clause_label, page_number=page.page_number, lines=[line])
            else:
                if current is None:
                    current = _Section(clause_ref=None, page_number=page.page_number)
                current.lines.append(line)

            prev_was_allcaps = is_allcaps

    if current and current.lines:
        sections.append(current)
    return sections


def _chunk_section(section: _Section) -> list[Chunk]:
    words = " ".join(section.lines).split()
    if not words:
        return []

    if len(words) <= MAX_SECTION_WORDS:
        return [Chunk(
            text=" ".join(words),
            chunk_type="prose",
            page_number=section.page_number,
            clause_ref=section.clause_ref,
        )]

    # Oversized section: sub-split by word count, overlap kept within this
    # section only — never allowed to pull in the next section's content.
    chunks = []
    start = 0
    n = len(words)
    while start < n:
        end = min(start + TARGET_WORDS, n)
        chunks.append(Chunk(
            text=" ".join(words[start:end]),
            chunk_type="prose",
            page_number=section.page_number,
            clause_ref=section.clause_ref,
        ))
        if end >= n:
            break
        start = max(end - OVERLAP_WORDS, start + 1)
    return chunks


def chunk_prose(pages: list[PageText]) -> list[Chunk]:
    sections = _split_into_sections(pages)
    chunks = []
    for section in sections:
        chunks.extend(_chunk_section(section))
    return chunks


def _serialize_table(rows: list[list[str | None]]) -> str:
    lines = []
    for row in rows:
        cells = [(cell or "").replace("\n", " ").strip() for cell in row]
        lines.append(" | ".join(cells))
    return "\n".join(lines)


def chunk_tables(tables: list[PageTable], max_rows: int = 20) -> list[Chunk]:
    """Skips (doesn't attempt to fix) tables whose extracted text shows the
    "fake bold" doubling artifact (see extract_text.py's _looks_doubled).
    pdfplumber's extract_tables() has no use_text_flow-equivalent escape
    hatch the way extract_text() does, and a naive "collapse consecutive
    duplicate characters" fix is provably lossy on text with genuine double
    letters (e.g. "Commerce" -> doubled "CCoommmmeerrccee" -> naive collapse
    -> "Comerce", one 'm' short) -- there's no safe automatic fix, so the
    honest choice is to drop the table and say so, not silently store
    garbled duplicated text as if it were real content."""
    chunks = []
    dropped = 0
    for table in tables:
        if not table.rows:
            continue
        if len(table.rows) <= max_rows:
            text = _serialize_table(table.rows)
            if _looks_doubled(text):
                dropped += 1
                continue
            chunks.append(Chunk(text=text, chunk_type="table", page_number=table.page_number))
        else:
            header = table.rows[0]
            for i in range(1, len(table.rows), max_rows):
                group = [header] + table.rows[i:i + max_rows]
                text = _serialize_table(group)
                if _looks_doubled(text):
                    dropped += 1
                    continue
                chunks.append(Chunk(text=text, chunk_type="table", page_number=table.page_number))
    if dropped:
        print(f"chunk_tables: dropped {dropped} table chunk(s) with unfixable doubled-text rendering")
    return chunks


def _exclude_table_text(pages: list[PageText], tables: list[PageTable]) -> list[PageText]:
    """pdfplumber's extract_text() doesn't know about table regions, so table
    content gets picked up twice: once flat/unstructured via extract_text(),
    once clean/structured via extract_tables(). The flat version is strictly
    worse (loses column alignment, and long cell text that wraps across lines
    can look like a heading) — drop any prose line that matches a table
    cell's content on the same page, so each piece of content is embedded
    exactly once, in its best form."""
    tables_by_page: dict[int, list[PageTable]] = {}
    for t in tables:
        tables_by_page.setdefault(t.page_number, []).append(t)

    cleaned = []
    for page in pages:
        known_fragments = set()
        for table in tables_by_page.get(page.page_number, []):
            for row in table.rows:
                for cell in row:
                    if not cell:
                        continue
                    for sub_line in cell.split("\n"):
                        norm = sub_line.strip()
                        if len(norm) >= 8:
                            known_fragments.add(norm)

        kept_lines = [
            line for line in page.text.splitlines()
            if line.strip() not in known_fragments
        ]
        cleaned.append(PageText(page_number=page.page_number, text="\n".join(kept_lines)))
    return cleaned


def chunk_document(pages: list[PageText], tables: list[PageTable]) -> list[Chunk]:
    cleaned_pages = _exclude_table_text(pages, tables)
    cleaned_pages = strip_boilerplate(cleaned_pages)
    return chunk_prose(cleaned_pages) + chunk_tables(tables)


if __name__ == "__main__":
    from ingestion.language_filter import filter_english

    path = Path(sys.argv[1])
    pages = extract_text_by_page(path)
    pages = [PageText(p.page_number, filter_english(p.text)) for p in pages]
    tables = extract_tables_by_page(path)

    chunks = chunk_document(pages, tables)
    prose = [c for c in chunks if c.chunk_type == "prose"]
    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    print(f"{len(prose)} prose chunks, {len(table_chunks)} table chunks\n")

    for c in chunks:
        word_count = len(c.text.split())
        print(f"--- {c.chunk_type} | page {c.page_number} | {word_count} words | clause_ref={c.clause_ref} ---")
        print(c.text[:300])
        print()
