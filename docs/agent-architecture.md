# Agent Architecture — RFP Sentinel

*How many agents, what each one does, what tools it uses, and how they connect.*

---

## 1. The count: 3 real agents, 1 borderline case, 2 deliberate non-agents

| # | Name | Status |
|---|---|---|
| 1 | RFP Criteria Extraction | **Not an agent** — LLM-classified now (not regex anymore), but a fixed sequence of questions, no tool-selection judgment. See §2. |
| 2 | RFP Compliance Agent | **Yes — built, tested, running.** Search + classify, verdict depends on what's retrieved. |
| 3 | RFP Self-Consistency Agent (prohibited-practices check) | **Borderline — judgment-based, but single-tool.** See §4. |
| 4 | Bid Evidence Extraction Agent | **Yes — built and tested.** Same search + classify pattern as #2, pointed at a bid instead of the norms KB. Not yet wired into the live graph. |
| — | Deterministic Scoring Engine | **No** — fixed formula plus one explicitly-triggered random draw, no LLM, no judgment |

The bar for calling something an "agent" here isn't "it's a step in the pipeline" — it's **does it use more than one tool, and does its output change depending on what it discovers, rather than always computing the same thing.** Extraction asks the LLM the same three fixed questions for every candidate regardless of what it finds — real LLM use, but not agentic by this bar. The prohibited-practices check makes a genuine judgment call, but only calls one tool (classify, no search), so it sits in between.

---

## 2. RFP Criteria Extraction (`extract_rfp_criteria`) — LLM-classified, still not an agent

**Job**: turn an uploaded RFP PDF into a clean list of structured, checkable criteria, plus two separately-extracted lists: `required_documents` (document types the RFP demands) and `prohibited_practices` (GeM's own listed buyer drafting-mistakes for this RFP).

**How it works today**: the PDF extraction/chunking pipeline (`extract_text.py`, `extract_tables.py`, `language_filter.py`, `chunker.py`) pulls out clause-shaped chunks. Chunks that deterministically match the extracted `prohibited_practices` list (a normalized text-overlap check, not an LLM guess) are excluded outright — a real bug was found and fixed here: judging each of those items individually, out of context, made even a capable LLM misclassify several of them as real criteria, since the "these are buyer mistakes to avoid" framing gets lost per-item. For everything else, each surviving candidate goes through **three fixed LLM questions**, run concurrently in a bounded pool (5 at a time — tested against a real concurrency ceiling, not an arbitrary number):
1. Is this a real requirement or generic guidance text? (Stage 1 — a cheap filter)
2. Mandatory or optional? (Stage 2, only for what survived Stage 1)
3. Which category — technical / financial / eligibility / **other**? (Stage 2)

`"other"` is a deliberate, honest 4th option — the three named categories don't cover every real RFP clause (e.g. a quantity-split ratio), and forcing a bad fit caused a real crash during testing (the model answered `'none'`, an out-of-vocabulary word, and the retry logic exhausted itself on the identical question three times). Adding a genuine escape hatch fixed it correctly instead of just prompting harder.

**Why it's still not an agent**: no tool-selection judgment — every candidate gets asked the same three questions in the same order, regardless of what's discovered. It's real LLM classification, just not agentic by this doc's own bar.

**Output**: a `StructuredRFP` (criteria, required_documents, prohibited_practices) — stored inside LangGraph's Postgres checkpoint, returned by `GET /rfp/{id}/criteria` and (for `required_documents`) `GET /bidder/rfps/{id}`.

---

## 3. RFP Compliance Agent (`check_rfp_compliance`)

**Job**: for every extracted criterion, decide whether it conflicts with the government norms knowledge base — *before* the buyer sees the RFP as final.

**Tools it uses**:
1. **Search** (`search_active()`) — retrieves the norm clauses relevant to this specific criterion, filtered to only currently-active regulations.
2. **The LLM classifier** (`ollama_client.classify`) — reads the criterion against what was retrieved and produces `compliant` / `violation` / `unclear`.

A deterministic numeric-threshold checker (`threshold_check.py`) used to sit in front of the classifier here, added because the original local model reliably got numeric comparisons backwards (e.g. correctly identifying 12% > 10%, then still concluding "fail" against a 10% minimum) — even at zero randomness, reproducible, unfixed by two rounds of prompt changes. It's been **removed**: switching to a larger remote model, confirmed via a controlled side-by-side test to get the same cases right, made the workaround unnecessary.

**The decision it makes**: search, then classify against what came back — a violation is only ever surfaced if the model points at a real citation; an uncited "violation" is discarded, never shown to the buyer as a false flag.

**Output**: `compliance_issue` + `compliance_citation` on the flagged `Criterion`, feeding into **Checkpoint A**.

---

## 4. RFP Self-Consistency Agent (`check_prohibited_practices`) — new, borderline case

**Job**: check the RFP's own extracted criteria against **its own** listed buyer drafting-mistakes (extracted in §2) — e.g. does this RFP actually name a specific brand, or ask for a Tender fee, things GeM's own rules say void a bid if present.

**Why this exists**: it grew directly out of fixing the extraction bug in §2. Once the prohibited-practices list was extracted as its own clean field instead of being guessed at per-chunk, the obvious next step was to actually *use* it — check the RFP's real criteria against it, the same way `check_rfp_compliance` checks against the external norms KB, just pointed at a list specific to this one RFP.

**Tools it uses**: just the LLM classifier — no search, since the list is short (≤14 items) and fits directly in the prompt as references. This is why it's a *borderline* case rather than a clean agent by this doc's bar: single tool, but the verdict still genuinely depends on what's found, not a fixed answer. Verified against real data with a mix of results, not uniformly clean: 3 of 22 real criteria flagged, including one confirmed false positive (a technical spec line mistaken for a specific-brand mention) — a reminder this stays a suggestion for Checkpoint A, never an automatic rejection.

**Output**: `prohibited_practice_issue` + `prohibited_practice_citation` on the flagged `Criterion`, rendered separately from `compliance_issue` in the buyer dashboard (labeled "RFP self-check" vs. "Norm conflict") so the buyer knows which kind of concern it is.

---

## 5. Bid Evidence Extraction Agent (`retrieve_and_extract_evidence`) — built, not yet wired into the live graph

**Job**: for every criterion the buyer approved, decide whether a specific bidder's Packet-I (technical) documents satisfy it.

**Tools it uses**: the same search + classify pattern as §3, pointed at a bid instead of the norms KB — `search_bid()`, always filtered to one `bid_id` **and** `packet="I"` by default, so financial content can never leak into a technical evaluation even if a caller forgets to specify a packet (proven directly: a call with no packet argument never returned Packet-II content in testing, even when it was the better semantic match).

**The decision it makes**: for each criterion, retrieve the bid's relevant content, classify: `pass` / `fail` / `partial`. Zero matches retrieved → deterministic `not_found`, no LLM call at all. A verdict with no real citation gets downgraded to `not_found` too — never a guess presented as a finding.

**Status**: built and verified against real data (a real RFP, a real bidder's submission), but **not yet wired into `build_graph.py`** the way §3 and §4 are — it currently runs as a standalone script, called from bid-evaluation testing, not from the live buyer-facing pipeline.

**Output**: an `EvidenceItem` per (bid, criterion) — feeds `scoring.py`'s Stage 1.

---

## 6. The Deterministic Scoring Engine — built, deliberately not an agent

**Job**: turn `EvidenceItem` verdicts into a pass/fail gate and a ranked shortlist.

**No tools. No LLM.** Every input always produces the same output, with one exception explained below:
- **Stage 1 (technical gate)**: any mandatory criterion `fail` → the bidder is out. Mandatory `not_found` → held for human review, never auto-failed. A `technical_score` is computed too, but only from technical/financial/other criteria — eligibility criteria are gate-only, not part of the weighted score.
- **Stage 2 (rank)**: MII filter (exclude non-local suppliers) → price rank → MSE price-match, using a price-band percentage and quantity-split ratio read from the specific RFP's own ATC text (never a hardcoded constant — a real NIELIT RFP proved a single RFP can override the general policy's 25%/25-75 default with its own 15%/60-40 clause).
- **A tied L1 price is surfaced, never silently resolved** — `run_l1_selection()` mirrors a real, documented GeM mechanism (a buyer-triggered random draw, MSE-priority-aware if MSE preference is active), sourced from GeM's own site rather than invented. This is the one place randomness enters the system, and it's explicit and buyer-triggered, not a hidden default. A real bug was caught and fixed here too: the MSE price-match logic used to guess an answer when a tie had *mixed* MSE status (some tied bidders MSE, some not) — it now correctly refuses to auto-resolve that case, waiting for the tie to be broken first.
- **QCBS (price + technical quality blended) was deliberately left out.** Every real RFP seen so far uses L1 only, nothing extracts `evaluation_method` from RFP text yet, and for spec-compliance-driven procurement (this project's actual Electronics-category scope), "quality" mostly collapses to binary checklist compliance — QCBS's blended score may add little over L1 here. Tracked in `ROADMAP.md`, not silently missing.

**Status**: built with a real pytest suite (`tests/test_scoring.py`), not just a smoke test — the one part of this system with zero LLM/Qdrant dependency, fully unit-testable with fixtures. **Not yet wired into `build_graph.py` or any API endpoint.**

This feeds a planned **Checkpoint B** (not built), where the evaluator would confirm the shortlist — the system never auto-selects a winner.

---

## 7. Full flow, agents and checkpoints together

```
RFP PDF uploaded
      │
      ▼
Criteria Extraction (LLM-classified, NOT agentic — fixed question sequence)  ──uses──▶ PDF pipeline + LLM classifier
      │
      ▼
[Agent] RFP Compliance Check  ──uses──▶  Search (norms KB) + LLM Classifier
      │
      ▼
[Borderline agent] RFP Self-Consistency Check  ──uses──▶  LLM Classifier (no search — small fixed list)
      │
      ▼
◆ CHECKPOINT A (human) — buyer reviews flagged criteria, approves/edits          ◀── built & working today
════════════════ everything below is built and individually tested, not yet wired into this graph ════════════════
      │
      ▼
Bidder PDF(s) uploaded (Packet-I/II sealed)
      │
      ▼
Document-Completeness Check (deterministic, no LLM — filename presence only)
      │
      ▼
[Agent] Bid Evidence Extraction  ──uses──▶  Search (bid, Packet-I only) + LLM Classifier
      │
      ▼
Deterministic Scoring Engine (not an agent) — Stage 1 gate → Stage 2 rank (incl. run_l1_selection on a tie)
      │
      ▼
◆ CHECKPOINT B (not built) — evaluator confirms shortlist
      │
      ▼
Confirmed shortlist + full audit trail

════════════════ read-only, separate track ════════════════
Bidder login ──▶ GET /bidder/rfps, GET /bidder/rfps/{id}  (published RFPs + required-documents checklist)
```

**LangGraph's role in this**: it's the conductor, not a worker — it calls each node in order, passes state between them, and — critically — pauses the entire flow at Checkpoint A (potentially for hours or days) and resumes exactly where it left off once a human responds. This pause/resume-later capability is why LangGraph specifically was chosen, not built by hand.

---

## 8. Quick answer for an interview

> "There are three real agents and one borderline case in this system, all built on the same underlying pattern: retrieve relevant reference material, then ask an LLM to classify against it, never surfacing a verdict without a real citation behind it. RFP compliance-check searches a government norms knowledge base; a newer self-consistency check compares the RFP against its own listed drafting-mistakes, using a small fixed reference list instead of search since there's no need for retrieval over 14 items; bid evidence-extraction does the same search-and-classify pattern against a bidder's sealed technical documents. Criteria extraction itself is LLM-based now too, but it's *not* agentic by our own definition — it asks the same three fixed questions every time, no tool-selection judgment, so we don't overclaim it. The final scoring engine is deliberately *not* an agent — pure Python, unit-tested, because a government-audited ranking has to be a formula you can point at, not a model's opinion. The one place randomness legitimately enters the system is a tied lowest-price bid, and even that's not invented — it mirrors GeM's own documented random-draw tie-break mechanism, triggered explicitly by the buyer, never automatic."

If pushed on why the deterministic threshold-checker was removed: *"It existed because the original small local model reliably got numeric comparisons backwards, even at zero temperature — a reproducible, model-specific weakness, not a prompt problem. We moved that comparison to plain code as a workaround. After switching to a larger remote model, we ran the exact same test side by side and confirmed the new model gets it right without the workaround, so we removed it rather than keep unnecessary code around — determinism was the right call *for that model*, not a universal rule that every LLM needs a math bypass."*

If pushed on the biggest known gap: *"The bid-evaluation half — evidence extraction and scoring — is built and individually tested against real data, but it's not wired into the same live graph the buyer-side steps run through yet. It's proven machinery sitting one integration step away from being part of the real pipeline, not a design gap."*
