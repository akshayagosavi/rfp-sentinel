"""
M3: extract per-page tables from a PDF using pdfplumber.

Tables come back as raw row lists here — chunker.py (M5) is responsible for
serializing them into embeddable text. table_settings is an escape hatch for
documents whose tables the default detection misses (borderless/whitespace
tables); pass a per-document override when that happens, not a rewrite.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

import pdfplumber


@dataclass
class PageTable:
    page_number: int
    table_index: int
    rows: list[list[str | None]]


def extract_tables_by_page(
    pdf_path: Path,
    table_settings: dict | None = None,
    page_range: tuple[int, int] | None = None,
) -> list[PageTable]:
    """page_range (1-indexed, inclusive) -- see extract_text_by_page()."""
    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        start, end = page_range if page_range else (1, len(pdf.pages))
        for page_num, page in enumerate(pdf.pages, start=1):
            if page_num < start or page_num > end:
                continue
            found = page.extract_tables(table_settings=table_settings)
            for idx, rows in enumerate(found):
                tables.append(PageTable(page_number=page_num, table_index=idx, rows=rows))
    return tables


if __name__ == "__main__":
    path = Path(sys.argv[1])
    result = extract_tables_by_page(path)
    if not result:
        print("No tables detected.")
    for table in result:
        print(f"--- page {table.page_number}, table {table.table_index} ---")
        for row in table.rows:
            print(row)
        print()
