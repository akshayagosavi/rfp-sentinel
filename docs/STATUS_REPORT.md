# RFP Sentinel — Status Report

*A snapshot of what's built, verified, and what's left — for tracking progress against the v1 plan, not a viva/architecture document (see `docs/RFP-Sentinel-Overview.pdf` for that).*

---

## Where we are, in plain language

This project has two big jobs.

**Job 1 — "Is this tender itself fair and legal?"** ✅ **Fully done.** A buyer uploads their tender PDF, the system pulls out the requirements, checks each one against real government rules, and shows the buyer anything that looks wrong before it gets published. Tested end-to-end on a real government tender.

**Job 2 — "Does this bidder's paperwork actually prove they qualify?"** 🟡 **More than halfway done.** Five pieces:
1. Safely storing a bidder's documents (keeping price documents hidden from the technical check, like a sealed envelope) — **done, tested.**
2. A fast first check — did the bidder submit every required document *type* at all, before we even look at content — **done, tested.**
3. Actually checking each requirement against the bidder's documents in depth — **done, tested.**
4. Turning all those individual checks into a final ranking (cheapest + qualified + small-business preference) — **not built yet.**
5. The actual buttons and screens to use any of this without running scripts by hand — **partly built** (buyer side is a real dashboard; a bidder-facing dashboard now exists on the backend, its screens are not built yet).

One extra thing worth knowing: we switched the AI model mid-project, from a small model running on this laptop to a larger one (`qwen2.5:7b`) running on a trusted remote server. Tested side by side: it's faster *and* it fixed a real accuracy bug the small model had (getting simple "is 12% ≥ 10%" comparisons backwards). That let us delete a whole workaround file we'd built specifically to cover for the small model's mistake.

---

## Where we are, in one paragraph (more technical)

The **buyer-side half of v1 is complete and working end-to-end** (RFP upload → criteria extraction → norm compliance check → human checkpoint with override → publish). The **bid-evaluation half** now has ingestion, Packet-I/II separation, a document-completeness checklist, and the evidence-extraction agent all built and verified against real documents. The LLM backing every classification step moved from a local `llama3.2:3b` to a remote `qwen2.5:7b`, verified faster and more accurate on the exact case that used to fail. A read-only **bidder-facing API** (login, list published RFPs, view required documents) is also now built. What's left to reach a complete v1 is the deterministic scoring engine, wiring everything into one continuous graph, and the remaining UI pages (bidder dashboard screens, bid upload, Checkpoint B).

---

## Step-by-step: how each stage actually works

### Stage 1 — RFP goes in, gets checked against government norms (buyer side)

i) Buyer uploads an RFP PDF via `POST /rfp/upload` (`backend/api/rfp.py`). The file is saved to `data/rfps/{rfp_id}_{filename}`, and a background task starts the graph.

ii) `extract_rfp_criteria()` (`backend/graph/extract_rfp_criteria.py`) turns the PDF into structured pieces:
   - `extract_text_by_page()` + `extract_tables_by_page()` (`ingestion/extract_text.py`, `ingestion/extract_tables.py`) pull raw text and tables page by page, auto-detecting and fixing a "doubled text" PDF rendering bug as they go.
   - `filter_english()` strips Devanagari (Hindi) text so only English flows into chunking.
   - `chunk_document()` (`ingestion/chunker.py`) splits the cleaned text into clause-aware chunks — never splitting one numbered clause across two chunks — plus separate table chunks.
   - Each qualifying prose chunk (has a clause reference, isn't guidance boilerplate, long enough) becomes one `Criterion`, with `mandatory`/`category` guessed by keyword regex (a fast heuristic, not an LLM call — see the hardcoded-shortcuts list below).
   - Separately, `_extract_required_documents()` reads the RFP's own "Document required from seller" line into `required_documents`.

iii) `check_rfp_compliance()` (`backend/graph/check_rfp_compliance.py`) checks each criterion against the norms already stored in Qdrant:
   - Embed the criterion's text (`embed_text()`, via Ollama's `nomic-embed-text`).
   - `search_active()` (`backend/rag/qdrant_client.py`) searches the `norms` Qdrant collection, filtered to `status=active`, top 2 matches.
   - Send the criterion + those 2 matched norm clauses to the LLM (`classify()` in `backend/llm/ollama_client.py`): compliant / violation / unclear.
   - A "violation" is only kept if the model actually cited one of the matched clauses — an uncited violation is discarded, never shown to the buyer as a false flag.

iv) The `checkpoint_a` graph node pauses the run (Postgres-backed, so it survives a server restart). The buyer reviews any flagged criteria, can override with a typed reason, and approves → the graph resumes → `status` becomes `"approved"` (this is what "published" means everywhere else in the system, including Stage 6).

### Stage 2 — Bidder's documents go in, split and stored so nothing leaks early

i) The bid's PDFs are uploaded via `ingest_bid.py`, each one tagged `I:file.pdf` (technical / Packet-I) or `II:file.pdf` (financial / Packet-II) — GFR Rule 189's "two sealed envelopes" rule.

ii) Each file goes through the same extract → filter → chunk pipeline as Stage 1, then:
   - `embed_texts_safely()` embeds every chunk, skipping (never crashing on) any chunk that breaks embedding.
   - `upsert_bid_chunks()` (`backend/rag/qdrant_client.py`) stores each chunk in the `bids` Qdrant collection, tagged with `bid_id`, `rfp_id`, `packet` ("I"/"II"), and `source_file`.

iii) The seal itself: `search_bid()` always filters by `bid_id` **and** `packet`, and **defaults to `packet="I"`** — so any code that forgets to specify a packet can only ever see technical content, never financial. Proven directly: a call with no packet argument never returned Packet-II content even when it was the closer match.

### Stage 3 — Quick check: did the bidder submit the right document types at all?

i) `_extract_required_documents()` already gave us the RFP's required document-type list (Stage 1.ii).

ii) `get_bid_source_files()` lists the distinct filenames the bidder uploaded for Packet-I.

iii) `check_document_completeness()` (`backend/graph/check_document_completeness.py`) does a cheap filename-based match (normalized, substring-based) between the two lists — no PDF content is opened here. Output: which required types are `present` (with which file matched) and which are `missing`.

iv) Deliberately **not** a hard gate — a "missing" result is meant to be glanced at and cleared by a human in seconds (e.g. "that's actually inside their ATC.pdf"), never an automatic rejection. Known limitation: a bidder who merges several required documents into one combined PDF, or submits a scanned/image PDF, would show false "missing" results here. The chosen fix is a process rule (ask bidders to upload one clearly-named file per required document type — see Stage 6), not a code fix, since a real content-level fix would need OCR + content-based document detection, both deliberately deferred.

### Stage 4 — Does the bidder's content actually satisfy each criterion?

i) `retrieve_and_extract_evidence()` (`backend/graph/retrieve_and_extract_evidence.py`) loops over the RFP's approved criteria (not the bid's chunks) — this guarantees every criterion gets checked exactly once and bounds the number of LLM calls to the criteria count.

ii) For each criterion: embed its text, then `search_bid(..., packet="I", top_k=2)` for the closest matching bid content.
   - Zero matches → deterministic `not_found`, no LLM call at all.
   - Matches found → send criterion + matched bid content to the same `classify()` function from Stage 1: pass / fail / partial.
   - If the model can't ground its answer in a real citation, the final verdict is downgraded to `not_found` regardless of which word the model picked — never a guess presented as a finding.

iii) Result: one `EvidenceItem` per criterion, each carrying a verdict + reasoning + citation (or lack of one).

### Stage 5 — Turning evidence into a shortlist (designed, not built yet)

i) Stage-1 gate: any mandatory criterion with verdict `fail` → bidder is out. Mandatory `not_found` → held for human review, never auto-failed (same philosophy as Stage 3's completeness check).

ii) Stage-2 rank, for bidders that passed the gate: apply MII (Make-in-India) filtering first, then rank by price (Packet-II, opened only at this point), then apply MSE price-matching using whatever percentage the RFP's own ATC clause specifies — never a hardcoded 20/25/40%, since the real NIELIT RFP proved that number can vary per-RFP and the RFP's own override clause always wins.

iii) Pure Python, zero LLM/Qdrant calls by design — the one part of the system meant to be fully unit-testable with fixtures.

### Stage 6 — Letting a bidder see what they need to submit (just built)

i) Bidder logs in (`POST /auth/login`) — a separate demo credential from the buyer's, role baked into the JWT (`backend/auth.py`).

ii) `GET /bidder/rfps` (`backend/api/bidder.py`) lists every RFP that has reached `status="approved"` — found by scanning `data/rfps/` and checking each one's existing graph state, no separate database table needed at today's scale.

iii) `GET /bidder/rfps/{id}` returns that RFP's category, evaluation method, criteria count, and its `required_documents` checklist — the same data Stage 1 already extracted, just re-shaped for a bidder to read. The intended pairing (not yet built as UI): show this alongside upload instructions asking the bidder to submit one clearly-named file per required document, to sidestep Stage 3's merged-file/scanned-file limitation by process rather than more engineering.

---

## The model swap: local llama3.2:3b → remote qwen2.5:7b

Switched `OLLAMA_BASE_URL` to a trusted remote server and the LLM model to `qwen2.5:7b` (embedding model unchanged: `nomic-embed-text`, still 768-dim). Verified with a direct, controlled side-by-side (identical code, identical test case — a 12%-discount bid against a 10%-minimum clause):

| | local llama3.2:3b | remote qwen2.5:7b |
|---|---|---|
| Time per LLM call | ~9.3s | ~4.2s |
| Verdict on the 12%-vs-10% test | fail (**wrong**, 5/5 runs) | pass (**correct**, 5/5 runs) |

Faster **and** more accurate, on the exact case that used to fail — better remote hardware more than compensating for a bigger model.

**Consequence**: `backend/scoring/threshold_check.py` — a deterministic regex-based percentage-threshold checker, built at M8 specifically to work around llama3.2:3b's backwards numeric reasoning — has been **removed**. Both call sites (`check_rfp_compliance.py`, `retrieve_and_extract_evidence.py`) now go straight to the LLM classifier. Re-verified end-to-end against real data after removal.

One real bug this surfaced and fixed: `retrieve_and_extract_evidence.py`'s prompt used to literally mention the word "not_found" while explaining what *not* to do — llama3.2:3b never picked up on it, but qwen2.5:7b, being more instruction-literal, started outputting that exact (invalid, for this call) word and crashing after retries. Fixed by rewording the instruction to never name a label outside the model's actual allowed options.

**Tradeoff worth remembering**: bid/RFP content now leaves this machine and goes to the remote server for every LLM call — the same data-locality question the original local-first design was meant to avoid, reopened by this switch. Accepted as-is since the server is trusted, but worth keeping in mind if that changes.

---

## Other hardcoded shortcuts that may no longer be needed (audit, not yet acted on)

These were built specifically because the local model was slow and/or unreliable. Worth revisiting now that the remote model is both faster and more accurate — listed here, not yet changed, since each is its own small decision:

| Shortcut | Where | Why it existed | Worth doing now? |
|---|---|---|---|
| `top_k=2` retrieval cap | `check_rfp_compliance.py`, `retrieve_and_extract_evidence.py` | "long prompts were timing out" on the local model | Could raise to 3-5 for richer context, now that prompts run faster |
| `criterion.text[:600]` truncation | same two files | "long clauses were making prompts too slow" | Could send full criterion text now — avoids losing context on long clauses |
| Keyword-regex `mandatory`/`category` inference (`_infer_mandatory`, `_infer_category`) | `extract_rfp_criteria.py` | Explicitly flagged in the file's own docstring as a speed shortcut to avoid "a new untested LLM dependency" at the time | Now a reasonable candidate for an LLM-based classification call, since the dependency is no longer new or untested |
| `_GUIDANCE_SECTION_MARKER` regex (detecting buyer-boilerplate vs. real criteria) | `extract_rfp_criteria.py` | Pattern-matched against one real document only, documented as possibly not generalizing | Could ask the LLM per-chunk "is this a real criterion or boilerplate," more robust across RFP templates |

**Deliberately excluded from this list** — these solve real-world PDF/data-quality problems, not model-reasoning limitations, so a better LLM doesn't change them: the text-doubling auto-detector, the embedding character cap, `embed_texts_safely()`'s skip-and-log behavior, and the document-completeness checklist's filename-based matching (that one was a deliberate *avoid-the-LLM* design choice from the start, not a workaround for a weak one — see Stage 3.iv above for why a stronger model would still need OCR to fully fix its known gap).

---

## What's built and verified

### Knowledge base (norms) — complete for what's sourced
- **6 real government documents, 968 chunks**, in Qdrant's `norms` collection: GeM GTC, MSME Policy 2012, MeitY CRS Handbook, GFR 2017 Chapter 6 (procurement-relevant pages only), and both DPIIT Make-in-India orders (2020-06-04 + 2020-09-15).
- Norm versioning (`active`/`superseded`) proven end-to-end.
- Still missing: a dedicated BIS CRS product list (no single downloadable source exists), and one memo (OM F.1/4/2021-PPD) that's only available as an unreadable scan.

### RFP evaluation pipeline — complete, tested against a real RFP
- Upload → extract criteria (rule-based, no LLM) → compliance-check against norms → Checkpoint A (human review, with a working **override + reasoning** flow) → publish.
- React dashboard (buyer role), FastAPI backend, JWT auth, LAN-reachable.

### Bid evaluation pipeline — verified against real data
- **`ingest_bid.py`**: a bidder's multi-document submission → Qdrant `bids` collection, isolated by `bid_id`.
- **Packet-I/Packet-II separation**: `search_bid()` defaults to Packet-I only (GFR Rule 189's seal enforced structurally, not by convention).
- **Document-completeness checklist** (`check_document_completeness.py`, new): fast filename-based presence check, verified against real data — correctly showed missing document types for a genuinely incomplete real submission.
- **`retrieve_and_extract_evidence()` (M11)**: verified against a real RFP and a real bidder's submission, producing grounded pass/fail/partial/not_found verdicts with citations.
- **Soft-delete lifecycle** (`close_bid()`) built; the hard-delete purge script is not.

### Bidder-facing API — new this phase
- Role-based login (buyer/bidder, separate demo credentials, role baked into the JWT).
- `GET /bidder/rfps` (list published RFPs), `GET /bidder/rfps/{id}` (summary + required-documents checklist).
- Verified live, including that role gating works in both directions (a bidder token gets 403 on buyer routes and vice versa).
- Frontend screens for this not yet built (see below).

### Ingestion robustness — hardened against real-world PDF messiness
- Auto-detection of the "fake bold" text-doubling artifact, page by page.
- Table chunks that can't be safely fixed are dropped, not silently stored garbled.
- A defensive character cap plus a general "never let one bad chunk crash the whole run" safety net.

---

## Current data in the system
| Store | Contents |
|---|---|
| Qdrant `norms` | 968 chunks, 6 documents |
| Qdrant `bids` | 206 chunks, 1 real bid (MEK Peripherals, tagged Packet-I/II) |
| Postgres | RFP criteria for the real NIELIT RFP (multiple test evaluations run against it) |

Note: the one RFP currently marked `"approved"` in the system was extracted before `required_documents` existed as a field, so `GET /bidder/rfps/{id}` shows an empty checklist for it today — a fresh upload/approve run would populate it correctly.

---

## What's not built yet

| Item | Status |
|---|---|
| Deterministic scoring engine (Stage 1 gate, Stage 2 ranking incl. MII filter → price rank → MSE price-match) | Not started. Design settled. |
| Wiring evidence-extraction + document-completeness + scoring into `build_graph.py` | Not started — currently standalone scripts, not part of the LangGraph pipeline. |
| Bidder dashboard UI (login page, RFP listing, RFP detail/checklist page) | Backend done, frontend not built. |
| Bid upload UI, evaluation progress page, Checkpoint B | Not built. |
| Clarification loop (2-day pause on an unclear criterion) | Designed, deliberately deferred — needs LangGraph cycle support. |
| Purge script (hard-delete after the 7-day grace window) | Not built. |
| Admin dashboard, multi-bidder self-service auth beyond one demo credential | Not started, correctly out of scope until later. |
| OCR for scanned documents | Not built — a proven, recurring blocker (hit 3 times across different real documents), also the root cause of Stage 3's known limitation. |

---

## Honest completion estimate

- **Buyer-side v1 (RFP → Checkpoint A → publish): ~100% done.**
- **Bid-evaluation v1 (ingest → completeness check → evidence-check → score → Checkpoint B): a bit past half done.** Ingestion, completeness-checking, and evidence-extraction (the harder, more novel pieces) are built and proven against real data, now on a faster and more accurate model. Scoring and the remaining UI screens (the more mechanical half) remain.
- **v1 overall: roughly 75% complete** by milestone count, weighted toward the harder problems already being solved rather than easier remaining scaffolding.
