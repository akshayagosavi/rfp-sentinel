# Roadmap

Deferred scope, tracked deliberately so it's not forgotten — not a backlog to pull from early.

## Norm data follow-ups (near-term, not blocking current milestone)

- Source and ingest the **MSME Public Procurement Policy (MSEs) Amendment Order, 2018** (Gazette S.O. 5670(E), 9 Nov 2018) as its own document — changes the procurement target from 20% to 25% and adds a 3% women-owned-MSE sub-target, effective 1 April 2019. Currently only the unamended 2012 base order is ingested (flagged in `data/norms/manifest.json`). The copy found during research was a poor-quality OCR scan (page 1's bilingual header extracted as garbled text) — worth finding a cleaner digital-native source, or handling as a v2+ OCR case if not.
- Periodically re-check GeM GTC for a newer version (we caught 1.22 → 1.23 by chance while researching manifest metadata, not via any monitoring — there's no mechanism that would catch this automatically, by design, since the project doesn't crawl/poll GeM's servers).
- **Done**: GFR 2017 Chapter 6 (procurement, Rule 189 — only pages 40-56 of the 208-page document, the rest is unrelated budget/audit content) and both DPIIT Make-in-India orders (2020-06-04 revision + 2020-09-15 partial amendment — both stay active, the second only amends specific paragraphs of the first) are now ingested.
- Still missing: a dedicated BIS CRS product list (no single official downloadable document found — the authoritative source is the live `crsbis.in`/`bis.gov.in` portal, which lists products interactively rather than as one PDF).
- **The OM No. F.1/4/2021-PPD (MSME + Make-in-India concurrent application, cited twice in the real NIELIT RFP) could not be ingested — the downloaded copy is a pure scanned image (0 extractable characters on all 4 pages, one image per page).** This is the second real document hit by the same OCR gap already tracked below (the 2018 MSME Amendment scan) — worth prioritizing OCR fallback sooner rather than later, since this is now a recurring, not hypothetical, blocker. Needs either a cleaner digital-native source or OCR.
- **Policy to define later**: once the superseded-status mechanism (keep old norm versions, flip `status` instead of deleting) is actually in use for real evaluations, decide a retention rule for eventually removing old superseded PDFs from the `data/norms/` working folder (Qdrant's superseded *points* stay for audit regardless — this is only about whether the source PDF file itself needs to stick around locally indefinitely).

## Scoring engine (M12) follow-ups

- **QCBS (Quality and Cost Based Selection) evaluation method — deliberately left out of the first scoring build.** Every real RFP processed so far uses `evaluation_method="L1"` (lowest price wins), nothing extracts `evaluation_method` from RFP text yet, and QCBS's weighting (e.g. 70% technical / 30% price) and what "quality" means for GeM's Electronics/commodity category were still open questions during design — for spec-compliance-driven procurement, "quality" mostly collapses to binary checklist compliance, so QCBS's blended score may add little over L1 in this category. Only build if a real QCBS RFP is actually encountered.
- **Price-tie-breaking rule not sourced.** Checked the ingested norms knowledge base directly (GTC, GFR 2017 Ch. 6, DPIIT MII order) for a documented "what happens when two bidders quote the exact same price" rule — nothing on point was found. Rather than invent one, the scoring engine surfaces tied L1 bidders to the buyer dashboard for a human decision (with the tender committee) instead of auto-breaking the tie. Needs either a wider GFR search or a real procurement officer to confirm the actual rule.
- **MSE price-band percentage and quantity-split ratio are required parameters, not auto-extracted.** `apply_mse_price_match()` needs both numbers passed in (e.g. 15% band / 60% share for the real NIELIT RFP's own ATC override) — pulling these out of an RFP's raw clause text automatically (the same way `_extract_required_documents()` does for document types) is a separate, not-yet-built extraction step.
- **Bid price (Packet-II) is a required input, not auto-extracted.** `BidInput.price` is assumed as given; there's no equivalent of `retrieve_and_extract_evidence()` that reads a price out of a bidder's Packet-II documents yet.
- **MII (local-supplier) and MSE status per bidder are required inputs, not auto-derived.** No ingestion step currently tags a bid with these flags from its documents.

## v1.1

- Credential-based auth with three roles: Buyer, Admin, Bidder.
- Three dashboards (buyer/evaluator, admin, bidder).
- Bidder self-service upload (6–n bidders per RFP).
- RFP legitimacy check — flags RFP citations to norms with `status != active`.
- Plain-language RFP summary for bidders.

## v2+

- OCR fallback for scanned PDFs (v1 assumes digital-native text).
- Multilingual support beyond the current English-only / Hindi-stripped approach.
- Some GeM-generated PDFs (confirmed in at least one `data/rfps/` "Bid Document") embed Hindi glyphs without a proper Unicode character map — pdfplumber/pdfminer can't decode them at all, so they come out as raw `(cid:N)` placeholders instead of real Devanagari text or even garbled-but-present characters. `language_filter.py`'s Devanagari-codepoint strip can't catch this, since there's no actual Devanagari text to strip — the extraction itself loses that content. Doesn't affect v1 (all 3 real norm PDFs are cleanly encoded), but will surface again at M9 when RFP/bid documents from `data/rfps/` get ingested. Possible v2+ fixes: OCR fallback specifically for pages/cells with unmapped glyphs, or a manual cid-to-glyph lookup table for GeM's specific font.
- LlamaIndex hierarchical chunking / auto-merging retrieval layered under Qdrant.
- More robust auth (JWT/session-based) if the app moves beyond a single local machine.
- LangGraph `Send`-based parallel evidence extraction across bids/criteria.
- Concurrent-evaluator support (Postgres already removes the main blocker).
- Checkpoint B shortlist reordering in the UI (v1 is confirm-only).
- Interview with a real procurement officer for ground-truth validation.
- Presentation-style architecture diagram (interview/viva deliverable).
