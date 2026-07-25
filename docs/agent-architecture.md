# Agent Architecture — RFP Sentinel

*How many agents, what each one does, what tools it uses, and how they connect.*

---

## 1. The count: 4 real agents, 1 borderline case, 3 deliberate non-agents

| # | Name | Status |
|---|---|---|
| 1 | RFP Criteria Extraction | **Not an agent** — LLM-classified now (not regex anymore), but a fixed sequence of questions, no tool-selection judgment. See §2. |
| 2 | RFP Compliance Agent | **Yes — built, tested, wired into the live graph.** Search + classify, verdict depends on what's retrieved. |
| 3 | RFP Self-Consistency Agent (prohibited-practices check) | **Borderline — judgment-based, but single-tool.** See §4. |
| 4 | Bid Evidence Extraction Agent | **Yes — built, tested, and wired into `run_stage1_evaluation`.** Same search + classify pattern as #2, pointed at a bid instead of the norms KB. |
| — | Deterministic Scoring Engine | **No** — fixed formula plus one explicitly-triggered random draw, no LLM, no judgment |
| 5 | Bid Price Extraction | **Not an agent** — one fixed LLM call per bid ("find the total price"), no search, no tool choice. See §6a. |
| 6 | RFP Legitimacy Check | **Not an agent** — deterministic keyword matching against the norm knowledge base, no LLM at all. See §7. |
| 7 | RFP Summary Generation | **Not an agent** — one fixed LLM call, same shape every time. See §7. |

The bar for calling something an "agent" here isn't "it's a step in the pipeline" — it's **does it use more than one tool, and does its output change depending on what it discovers, rather than always computing the same thing.** Extraction asks the LLM the same three fixed questions for every candidate regardless of what it finds — real LLM use, but not agentic by this bar. The prohibited-practices check makes a genuine judgment call, but only calls one tool (classify, no search), so it sits in between. Price extraction and summary generation are both single, fixed LLM calls with no retrieval or tool choice at all — real LLM use, useful, but no more "agentic" than criteria extraction.

---

## 2. RFP Criteria Extraction (`extract_rfp_criteria`) — LLM-classified, still not an agent

**Job**: turn an uploaded RFP PDF into a clean list of structured, checkable criteria, plus several separately-extracted fields: `required_documents` (document types the RFP demands), `prohibited_practices` (GeM's own listed buyer drafting-mistakes for this RFP), `evaluation_method` (L1 or QCBS, read from the RFP's own "Evaluation Method" field), and `price_band_percent`/`mse_share_percent` (the RFP's own MSE purchase-preference numbers, read from its standard "L-1+ N% (Selected by Buyer)... awarded for M%... quantity" paragraph).

**How it works today**: the PDF extraction/chunking pipeline (`extract_text.py`, `extract_tables.py`, `language_filter.py`, `chunker.py`) pulls out clause-shaped chunks. Chunks that deterministically match the extracted `prohibited_practices` list (a normalized text-overlap check, not an LLM guess) are excluded outright. For everything else, each surviving candidate goes through **three fixed LLM questions**, run concurrently in a bounded pool (5 at a time — tested against a real concurrency ceiling, not an arbitrary number):
1. Is this a real requirement or generic guidance text? (Stage 1 — a cheap filter)
2. Mandatory or optional? (Stage 2, only for what survived Stage 1)
3. Which category — technical / financial / eligibility / **other**? (Stage 2)

The `evaluation_method`, `price_band_percent`, and `mse_share_percent` extractions are pure regex/keyword matching, not LLM calls — grounded against real RFP text before being trusted (the same RFP genuinely says "Total value wise evaluation" for its Evaluation Method field, mapped to `L1`; genuinely states "L-1+ 15% (Selected by Buyer)... 25% (selected by Buyer) percentage of total quantity" for the MSE numbers, correctly extracted as `15.0`/`25.0`). A second real RFP confirmed different real numbers (`15%`/`25%` vs. an earlier-seen `15%`/`60%`), proving these are genuinely RFP-specific, not something safe to hardcode.

**Why it's still not an agent**: no tool-selection judgment — every candidate gets asked the same three questions in the same order, regardless of what's discovered. It's real LLM classification, just not agentic by this doc's own bar.

**Output**: a `StructuredRFP` (criteria, required_documents, prohibited_practices, evaluation_method, price_band_percent, mse_share_percent) — stored inside LangGraph's Postgres checkpoint, read by every downstream endpoint (`GET /rfp/{id}/criteria`, `GET /bids/{id}`, `run_stage2_evaluation`, etc.).

---

## 3. RFP Compliance Agent (`check_rfp_compliance`)

**Job**: for every extracted criterion, decide whether it conflicts with the government norms knowledge base — *before* the buyer sees the RFP as final.

**Tools it uses**:
1. **Search** (`search_active()`) — retrieves the norm clauses relevant to this specific criterion, filtered to only currently-active regulations (the same `status` field the admin norm-management screen controls).
2. **The LLM classifier** (`ollama_client.classify`) — reads the criterion against what was retrieved and produces `compliant` / `violation` / `unclear`.

**The decision it makes**: search, then classify against what came back — a violation is only ever surfaced if the model points at a real citation; an uncited "violation" is discarded, never shown to the buyer as a false flag.

**Output**: `compliance_issue` + `compliance_citation` on the flagged `Criterion`, feeding into **Checkpoint A**, and now also visible on the admin's buyer-conduct oversight screen for any RFP that got published anyway.

---

## 4. RFP Self-Consistency Agent (`check_prohibited_practices`) — borderline case

**Job**: check the RFP's own extracted criteria against **its own** listed buyer drafting-mistakes (extracted in §2) — e.g. does this RFP actually name a specific brand, or ask for a Tender fee, things GeM's own rules say void a bid if present.

**Tools it uses**: just the LLM classifier — no search, since the list is short (≤14 items) and fits directly in the prompt as references. This is why it's a *borderline* case rather than a clean agent by this doc's bar: single tool, but the verdict still genuinely depends on what's found, not a fixed answer. Verified against real data with a mix of results, not uniformly clean: 3 of 22 real criteria flagged, including one confirmed false positive (a technical spec line mistaken for a specific-brand mention) — a reminder this stays a suggestion for Checkpoint A, never an automatic rejection.

**Output**: `prohibited_practice_issue` + `prohibited_practice_citation` on the flagged `Criterion`, rendered separately from `compliance_issue` in the buyer dashboard (labeled "RFP self-check" vs. "Norm conflict") so the buyer knows which kind of concern it is.

**A real enforcement gap found and fixed here**: the frontend's publish flow always required a buyer to type `override_reasoning` for every flagged criterion before letting a flagged RFP publish — but `POST /rfp/{id}/criteria/approve` itself never checked this, so a direct API call could bypass it entirely. Found live, via the admin buyer-conduct oversight screen (built afterward) showing the real demo RFP with flagged criteria and `override_reasoning: null` — traced to test rounds that called the API directly instead of clicking through the UI. Fixed by adding the same check server-side: the endpoint now rejects any flagged criterion missing a reasoning, regardless of caller.

---

## 5. Bid Evidence Extraction Agent (`retrieve_and_extract_evidence`) — wired into the live pipeline

**Job**: for every criterion the buyer approved, decide whether a specific bidder's Packet-I (technical) documents satisfy it.

**Tools it uses**: the same search + classify pattern as §3, pointed at a bid instead of the norms KB — `search_bid()`, always filtered to one `bid_id` **and** `packet="I"` by default, so financial content can never leak into a technical evaluation even if a caller forgets to specify a packet.

**The decision it makes**: for each criterion, retrieve the bid's relevant content, classify: `pass` / `fail` / `partial`. Zero matches retrieved → deterministic `not_found`, no LLM call at all. A verdict with no real citation gets downgraded to `not_found` too — never a guess presented as a finding. A classifier call that never produces a usable verdict at all (e.g. the model emits the literal string `"null"` instead of one of the allowed options, after exhausting retries) is also downgraded to `not_found` for that one criterion rather than crashing the whole bid's evaluation — a real bug found and fixed: it used to lose every other criterion's already-correct evidence for that bid.

**Status**: built, verified against real data, and **now called from `run_stage1_evaluation`**, triggered either by the closing-date timer or a buyer's manual "Close & Evaluate Now" — no longer a standalone script.

**Output**: an `EvidenceItem` per (bid, criterion), persisted to Postgres (`bid_evidence` table, one row per pair) — feeds `scoring.py`'s Stage 1, and is what a buyer reviews/resolves for any `not_found` mandatory criterion before financial bids can open.

---

## 6. The Deterministic Scoring Engine — wired, deliberately not an agent

**Job**: turn `EvidenceItem` verdicts into a pass/fail gate and a ranked shortlist.

**No tools. No LLM.** Every input always produces the same output, with one exception explained below:
- **Stage 1 (technical gate)**: any mandatory criterion `fail` **or** `partial` → the bidder is out — GeM's own technical evaluation gives no partial credit on a "must/shall" requirement, so a partial match is still non-compliance. Mandatory `not_found` → held for human review, never auto-failed, and **now actually enforced**: `POST /rfp/{id}/open-financial-bids` refuses to run Stage 2 while any Stage-1-passed bid still has an unresolved mandatory `not_found`. A `technical_score` is computed too, but only from technical/financial/other criteria — eligibility criteria are gate-only, not part of the weighted score.
- **Stage 2, L1**: MII filter (exclude non-local suppliers) → price rank → MSE price-match, using a price-band percentage and quantity-split ratio read from the specific RFP's own text (§2) — never a hardcoded constant, confirmed against two real RFPs with two different real numbers.
- **Stage 2, QCBS**: blends each Stage-1-passed bid's `technical_score` with a price score (cheapest bidder scores 100, others proportionally less) into one final score, ranked descending — unlike L1, technical quality keeps mattering after the gate. Branch chosen by the RFP's own extracted `evaluation_method`. No real QCBS RFP has been seen yet to validate the default 70/30 weighting against — tracked in `ROADMAP.md`.
- **A tied L1 price is surfaced, never silently resolved** — `run_l1_selection()` mirrors a real, documented GeM mechanism (a buyer-triggered random draw, MSE-priority-aware if MSE preference is active), sourced from GeM's own site rather than invented. This is the one place randomness enters the system, and it's explicit and buyer-triggered, not a hidden default.

**Status**: built with a real pytest suite (`tests/test_scoring.py`, 26 tests), the one part of this system with zero LLM/Qdrant dependency, fully unit-testable with fixtures. **Wired into `run_stage2_evaluation`**, triggered by the buyer's explicit "Open Financial Bids" action (separate from Stage 1's close, mirroring the real two-envelope principle — a technically disqualified bidder's price is never opened).

This feeds the buyer-facing ranked-results view (`RfpManage.jsx`) — L1 or QCBS depending on the RFP, plus the tie-break UI when `run_l1_selection` is needed. The system never auto-selects a winner without this explicit confirmation step.

---

## 6a. Bid Price Extraction (`extract_bid_price`) — one fixed LLM call, not an agent

**Job**: read the single total price figure out of a bidder's sealed financial document (Packet-II), once a buyer explicitly opens financial bids.

**Why it's not an agent**: one prompt, no search, no tool choice — the model is handed the full Packet-II text and asked for one number. No deterministic regex pre-pass either (unlike `check_rfp_compliance`'s old numeric-threshold checker) — extracting "the one total price" from a free-form price schedule is a harder pattern-matching problem than a plain threshold comparison, and the current model was already confirmed reliable at numeric reasoning.

**Verified against real currency-formatted text** (Indian-style comma grouping, e.g. "5,01,500.00"): extracted exactly `501500.0`, every time tested, across multiple real test documents with different totals.

**Output**: a price (or `None` if extraction genuinely failed after retries, excluding that bid from ranking rather than guessing) — persisted to `bids.price`, which stays `NULL` from submission until this runs.

---

## 7. Bidder-Facing Checks — RFP Legitimacy and Plain-Language Summary

Two read-only, bidder-facing features, neither an agent, both reusing infrastructure built for the buyer/evaluator side:

**`check_rfp_legitimacy`** — deterministic keyword matching, **no LLM at all**. Confirms the norms an RFP cites are still `active` in the knowledge base (the same `status` field the admin norm screen controls), not `superseded`/`withdrawn`. Grounded against a real RFP before writing any matching logic: it genuinely cites GeM's GTC, the 2012 MSME Order, and the 2017 Make-in-India Order, while correctly *not* claiming it cites GFR or the CRS Handbook. Verified to reflect *live* status changes: flipping a cited norm to `superseded` via the admin panel changed this check's result immediately, no caching involved.

**`generate_rfp_summary`** — one fixed LLM call (not a classification, a free-text generation), turning the RFP's extracted criteria into a 3-5 sentence plain-language explanation for a bidder who hasn't read the full PDF. Cached in Postgres (`rfps.summary`) after first generation, since the RFP's content is immutable once published — regenerating an identical summary on every page view would just be wasted LLM calls. First call took ~23s in testing; every call after that was instant (reading the cache).

---

## 8. Full flow, agents and checkpoints together

```
RFP PDF uploaded
      │
      ▼
Criteria Extraction (LLM-classified, NOT agentic) ──uses──▶ PDF pipeline + LLM classifier
  also extracts: evaluation_method, MSE price-band %/share % (deterministic, grounded in real text)
      │
      ▼
[Agent] RFP Compliance Check  ──uses──▶  Search (norms KB) + LLM Classifier
      │
      ▼
[Borderline agent] RFP Self-Consistency Check  ──uses──▶  LLM Classifier (no search — small fixed list)
      │
      ▼
◆ CHECKPOINT A (human) — buyer reviews flagged criteria, approves/edits.
  A flagged criterion published without override_reasoning is now REJECTED
  server-side, not just blocked by the UI.
      │
      ▼
Public bid listing/detail — anyone can browse, no login. Bidder-facing:
  RFP Legitimacy Check (deterministic, no LLM) + Plain-Language Summary
  (one fixed LLM call, cached) both available here.
      │
      ▼
Bidder self-signup, MSE/MII certs in Profile (declared once, not per bid),
submission under a blocking document-completeness gate, Packet-I/II sealed
      │
      ▼
closing_date timer (auto) OR buyer's manual "Close & Evaluate Now"
      │
      ▼
[Agent] Bid Evidence Extraction  ──uses──▶  Search (bid, Packet-I only) + LLM Classifier
      │
      ▼
Deterministic Scoring Engine, Stage 1 — mandatory fail/partial → out;
mandatory not_found → held for human review
      │
      ▼
◆ Buyer resolves every not_found mandatory criterion (required reasoning) —
  ENFORCED: Stage 2 cannot open while any remain unresolved
      │
      ▼
Buyer's explicit "Open Financial Bids" (separate action, mirrors the real
two-envelope principle — a disqualified bidder's price is never opened)
      │
      ▼
Bid Price Extraction (one fixed LLM call per bid, not agentic)
      │
      ▼
Deterministic Scoring Engine, Stage 2 — L1 rank + MSE price-match, or QCBS
blend, per the RFP's own evaluation_method
      │
      ▼
◆ Buyer resolves an L1 tie via run_l1_selection() if one exists
      │
      ▼
Final ranking, full audit trail

════════════════ admin surface, separate from the flow above ════════════════
Norm status control (active/superseded/withdrawn) ──▶ every check above respects it live
User management ──▶ deactivate = revoked on the very next request, any already-issued JWT included
Buyer-conduct oversight ──▶ every published RFP with a flagged-but-possibly-unjustified criterion
```

**LangGraph's role in this**: it's the conductor for the RFP-upload-through-Checkpoint-A portion — it calls each node in order, passes state between them, and pauses the entire flow at Checkpoint A (potentially for hours or days), resuming exactly where it left off once a human responds. Stage 1/2 evaluation runs as plain async functions triggered by explicit buyer actions (close, resolve, open-financial-bids) or the closing-date timer — no LangGraph interrupt needed there, since the "pause points" are just separate API endpoints a human calls when ready, not a mid-function suspend.

---

## 9. Quick answer for an interview

> "There are four real agents and one borderline case in this system, all built on the same underlying pattern: retrieve relevant reference material, then ask an LLM to classify against it, never surfacing a verdict without a real citation behind it. RFP compliance-check searches a government norms knowledge base; a self-consistency check compares the RFP against its own listed drafting-mistakes; bid evidence-extraction does the same search-and-classify pattern against a bidder's sealed technical documents, and it's actually wired into the live pipeline now, triggered by a closing-date timer or a buyer's manual override. Criteria extraction and bid-price extraction are LLM-based too, but neither is agentic by our own definition — fixed questions, no tool-selection judgment, so we don't overclaim it. Two bidder-facing features round it out: a legitimacy check that's pure deterministic keyword matching against the same norm knowledge base an admin controls, and a plain-language summary that's one cached LLM call. The final scoring engine is deliberately *not* an agent — pure Python, unit-tested, because a government-audited ranking has to be a formula you can point at, not a model's opinion. It supports both L1 and QCBS now, chosen by what the RFP itself says, and the one place randomness legitimately enters the system is a tied lowest-price bid, mirroring GeM's own documented random-draw tie-break mechanism, triggered explicitly by the buyer, never automatic."

If pushed on the biggest real bug found and fixed this way: *"Building the admin buyer-conduct oversight screen — which just displays which published RFPs have a flagged-but-unjustified criterion — immediately surfaced a real one on our own demo data: a flagged criterion published with no reasoning recorded. Tracing it back, the frontend's publish button always required that reasoning, but the backend endpoint itself never checked — it trusted whatever payload it was given. So a direct API call could bypass a rule the UI thought it was enforcing. We fixed it server-side the same day it was found, which is really the point of building an oversight tool at all: it's not just for catching bad actors, it catches gaps in your own enforcement you didn't know existed."*

If pushed on the biggest known gap: *"QCBS is fully built and wired — the scoring engine, the RFP-text extraction of which method a tender uses, all of it — but no real QCBS RFP has turned up in the real documents gathered during development to validate the default weighting against. Every real RFP we've seen states L1. The code path is exercised by unit tests with fixture data, just not by a real example from the wild yet."*
