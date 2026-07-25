# Roadmap

Deferred scope, tracked deliberately so it's not forgotten — not a backlog to pull from early.

## Norm data follow-ups (near-term, not blocking current milestone)

- Source and ingest the **MSME Public Procurement Policy (MSEs) Amendment Order, 2018** (Gazette S.O. 5670(E), 9 Nov 2018) as its own document — changes the procurement target from 20% to 25% and adds a 3% women-owned-MSE sub-target, effective 1 April 2019. Currently only the unamended 2012 base order is ingested (flagged in `data/norms/manifest.json`). The copy found during research was a poor-quality OCR scan (page 1's bilingual header extracted as garbled text) — worth finding a cleaner digital-native source, or handling as a v2+ OCR case if not.
- Periodically re-check GeM GTC for a newer version (we caught 1.22 → 1.23 by chance while researching manifest metadata, not via any monitoring — there's no mechanism that would catch this automatically, by design, since the project doesn't crawl/poll GeM's servers).
- Still missing: a dedicated BIS CRS product list (no single official downloadable document found — the authoritative source is the live `crsbis.in`/`bis.gov.in` portal, which lists products interactively rather than as one PDF).
- **The OM No. F.1/4/2021-PPD (MSME + Make-in-India concurrent application, cited in real RFP text seen during development) could not be ingested — the downloaded copy is a pure scanned image (0 extractable characters on all 4 pages, one image per page).** This is the second real document hit by the same OCR gap already tracked below (the 2018 MSME Amendment scan) — worth prioritizing OCR fallback sooner rather than later, since this is now a recurring, not hypothetical, blocker. Needs either a cleaner digital-native source or OCR.
- **Policy to define later**: once the superseded-status mechanism (keep old norm versions, flip `status` instead of deleting) is actually in use for real evaluations, decide a retention rule for eventually removing old superseded PDFs from the `data/norms/` working folder (Qdrant's superseded *points* stay for audit regardless — this is only about whether the source PDF file itself needs to stick around locally indefinitely).

## Scoring engine follow-ups

- **QCBS is built (`score_stage2_qcbs()`, wired into `run_stage2_evaluation()` via the RFP's own extracted `evaluation_method`), but its default 70/30 technical/price weighting has never been validated against a real QCBS RFP.** Every real RFP encountered during development uses `evaluation_method="L1"` — the extraction correctly reads this from each RFP's own "Evaluation Method" field, so a genuine QCBS RFP would be detected and scored correctly by the code, but the specific default weight split is a placeholder until a real example is found to check it against.
- **Other real procurement edge cases identified via research, not yet built, worth knowing for review/interview purposes**: arithmetic-discrepancy correction rules for price bids (unit price prevails over total unless an obvious decimal-point error, subtotals prevail over a wrong grand total, words prevail over figures unless the words themselves contain the error) — we don't validate/correct bid arithmetic at all currently; single-bid tenders are valid (not auto-invalid) if properly advertised and reasonably priced; abnormally low bids require a written justification from the bidder before rejection, per procurement manuals (GFR itself is silent); identical-price ties across many bidders can itself be a cartelization/collusion signal, a different lens than "who wins"; bidder blacklisting/debarment status isn't checked anywhere in this system; GTC Clause 26 (bidders from countries sharing a land border with India) is present in real RFP text we've seen but isn't enforced anywhere in the pipeline.

## v2+

- OCR fallback for scanned PDFs (v1 assumes digital-native text).
- Multilingual support beyond the current English-only / Hindi-stripped approach.
- Some GeM-generated PDFs (confirmed in at least one `data/rfps/` "Bid Document") embed Hindi glyphs without a proper Unicode character map — pdfplumber/pdfminer can't decode them at all, so they come out as raw `(cid:N)` placeholders instead of real Devanagari text or even garbled-but-present characters. `language_filter.py`'s Devanagari-codepoint strip can't catch this, since there's no actual Devanagari text to strip — the extraction itself loses that content. Possible v2+ fixes: OCR fallback specifically for pages/cells with unmapped glyphs, or a manual cid-to-glyph lookup table for GeM's specific font.
- LlamaIndex hierarchical chunking / auto-merging retrieval layered under Qdrant.
- LangGraph `Send`-based parallel evidence extraction across bids/criteria.
- Concurrent-evaluator support (Postgres already removes the main blocker).
- Interview with a real procurement officer for ground-truth validation.
- Presentation-style architecture diagram (interview/viva deliverable).
- Bidder-conduct flagging (a bidder flags a tender as unrealistic before bidding closes; repeated flags surface to Admin) — a distinct idea from the buyer-conduct oversight that's now built (which audits *published-with-a-flag* RFPs, not bidder-submitted complaints). Not started; would need a new flag-submission mechanism and a flags record.
- Email verification and password reset for real accounts.

## Recently completed (kept here briefly for continuity, not as an open item)

- Admin dashboard — all three planned capabilities: norm status management, user management (with real JWT revocation on deactivation, not just login-blocking), and buyer-conduct oversight (published RFPs with an unjustified flagged criterion) — including a server-side fix once the oversight screen surfaced that `POST /rfp/{id}/criteria/approve` wasn't actually enforcing the override-reasoning requirement itself.
- Bid price extraction from the bidder's sealed financial document (LLM-read at Stage 2, not a form field at submission).
- MSE price-band %/quantity-share % extraction from the RFP's own text (previously required manual input).
- `evaluation_method` (L1/QCBS) extraction from the RFP's own "Evaluation Method" field.
- Bidder-facing RFP legitimacy check (cited-norm status) and plain-language summary (LLM-generated, cached).
- The pending-criteria human-resolution gate before Stage 2 can open.
