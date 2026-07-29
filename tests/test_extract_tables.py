"""
Regression guard for the pdfplumber -> PyMuPDF table-detection migration.

pdfplumber's extract_tables() had two confirmed failure modes on real
documents: (1) it missed a real multi-column table entirely (the consignee/
delivery-schedule table on GeM-Bidding-Server 2 BIS.pdf page 8), which let
its content leak through as garbled prose; (2) it hallucinated tables out of
ordinary wrapped paragraphs and repeating page headers (GeM GTC page 12,
GFR2017 pages 40-56). These assertions pin PyMuPDF's find_tables() behavior
against the same real PDFs already committed under data/, so a future
library swap or config change can't silently reintroduce either failure mode.
"""
from pathlib import Path

from ingestion.extract_tables import extract_tables_by_page

RFP_PATH = Path("data/rfps/GeM-Bidding-Server 2 BIS.pdf")
GTC_PATH = Path("data/norms/GeM-GTC-40-1741175351.pdf")
GFR_PATH = Path("data/norms/GFR2017.pdf")


def test_consignee_table_detected_with_isolated_cells():
    # The originally-reported bug: this table was not detected at all by
    # pdfplumber, so "Sanjay Bathavar" leaked into prose interleaved with
    # unrelated row/column values ("1 Sanjay Bathavar 1 30").
    tables = extract_tables_by_page(RFP_PATH)
    page8 = [t for t in tables if t.page_number == 8]
    assert page8, "expected at least one table on page 8"
    matches = [row for t in page8 for row in t.rows if any(cell and "Sanjay Bathavar" in cell for cell in row)]
    assert len(matches) == 1
    row = matches[0]
    assert row[0] == "1"
    assert row[3] == "1"
    assert row[4] == "30"


def test_gtc_genuine_tables_still_detected():
    # Pages 11 and 17 hold GTC's two genuine tables (confirmed by direct row
    # dump); both libraries agree these are real.
    tables = extract_tables_by_page(GTC_PATH)
    pages = sorted(set(t.page_number for t in tables))
    assert 11 in pages
    assert 17 in pages


def test_gtc_wrapped_paragraphs_not_misdetected_as_tables():
    # pdfplumber previously mis-detected 7 ordinary wrapped paragraphs as
    # tables on these pages (e.g. page 12's "table" was just a consent
    # paragraph split across rows). None of these are real tables.
    tables = extract_tables_by_page(GTC_PATH)
    false_positive_pages = {12, 16, 19, 20, 25, 33, 34}
    detected_pages = set(t.page_number for t in tables)
    assert not (detected_pages & false_positive_pages)


def test_gfr2017_repeating_header_not_misdetected_as_table():
    # pdfplumber previously mis-parsed the repeating "Chapter - 6" running
    # header as a one-row table on every single page of this chapter.
    tables = extract_tables_by_page(GFR_PATH, page_range=(40, 56))
    assert tables == []
