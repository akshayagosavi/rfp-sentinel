# RFP Sentinel

A RAG-based bid-evaluation co-pilot for GeM (Government e-Marketplace) Technical Evaluators, scoped to the **Electronics category**. It serves the **buyer/evaluator side** of government procurement — every commercial RFP-AI tool on the market serves bidders responding to tenders; this is the other side of that transaction, a gap in the market. A light, read-only bidder-facing view (published RFPs + required-documents checklist) also exists, deliberately not a bid-writing tool, so it doesn't compete with the buyer-side thesis.

<img width="1920" height="925" alt="image" src="https://github.com/user-attachments/assets/67c1c3d5-fa5d-4ad4-abef-d9c7a15bff84" />
<img width="1920" height="925" alt="image" src="https://github.com/user-attachments/assets/1c7aa3a2-8ec6-42e9-9060-bbd0ad67d606" />
<img width="1920" height="925" alt="image" src="https://github.com/user-attachments/assets/7067c59d-22d3-4514-a54a-95d8f30c4e5d" />
<img width="1920" height="925" alt="Screenshot from 2026-07-21 23-44-49" src="https://github.com/user-attachments/assets/eff4c7bf-ad7a-4f69-8262-173019011d2d" />

A buyer uploads an RFP/tender PDF. The system extracts its requirements, checks them against a knowledge base of real government procurement norms (GeM's GTC, the MSME Public Procurement Policy, GFR 2017, DPIIT Make-in-India orders, MeitY's CRS handbook), separately checks the RFP against **its own** listed buyer drafting-mistakes, flags anything that conflicts with a citation, and pauses for a human to review before anything is published. Once bids come in, the same machinery checks each bidder's submission against the approved criteria and scores/ranks the survivors — that half is built and tested but not yet wired into one continuous flow (see [Current status](#current-status-v1-in-progress-roughly-87-complete)).

## Current status (v1, in progress — roughly 87% complete)

**Buyer side — ~99%, fully working end-to-end:**
- RFP PDF upload → criteria extraction (LLM-classified: guidance-vs-criterion, mandatory/optional, technical/financial/eligibility/other) → compliance check against the norms knowledge base → a **second, separate self-check** of the RFP's own criteria against GeM's own listed "buyer prohibited practices" (e.g. "don't name a specific brand," "don't ask for a Tender fee") → human checkpoint with override-and-reasoning → publish.
- LangGraph orchestrates the pipeline; Postgres is the checkpoint store; FastAPI serves it; a React dashboard drives it.
- Real, sourced logic for edge cases most systems get wrong by omission — e.g. `run_l1_selection()` implements GeM's own documented random-draw tie-break mechanism (MSE-priority-aware), not an invented rule.

**Bid evaluation — core logic ~75%, built and individually tested, not yet one connected pipeline:**
- Bid ingestion with a structural technical/financial (Packet-I/Packet-II) seal — `search_bid()` defaults to Packet-I, so a caller that forgets to specify a packet can never see pricing data, proven directly by testing.
- A fast document-completeness checklist (did the bidder submit the right document *types*, before checking content).
- Evidence extraction — does the bidder's content actually satisfy each approved criterion, with citations.
- A deterministic scoring engine (Stage 1 pass/fail gate, Stage 2 MII-filter → price-rank → MSE price-match) — zero LLM/Qdrant dependency, real pytest suite, not just a smoke test.
- Not yet done: wiring these four pieces into `build_graph.py` the way the buyer-side steps are, and auto-extracting the scoring engine's remaining manual inputs (MSE band %, bid price, MII/MSE flags).

**Bidder-facing — ~90%:** read-only login, a dashboard listing published RFPs, and a detail page showing the required-documents checklist with clear submission guidance. Backend and frontend both built; not yet visually verified in a browser.

**Not yet built:** Admin dashboard (norm management, buyer-conduct oversight, user management — see `ROADMAP.md`), bid upload UI, Checkpoint B, multi-user auth beyond one demo credential per role.

## Architecture

```
                     ┌─────────────────────┐
  Norm PDFs  ──────▶ │  Ingestion pipeline  │ ──▶ Qdrant (`norms` collection)
 (GTC, MSME, GFR,    │  extract → chunk →   │     — the permanent rulebook,
  MII orders, CRS)   │  embed → store       │       built once, ahead of time
                     └─────────────────────┘

                     ┌────────────────────────────────────────────────────────┐
  RFP PDF   ───────▶ │ LangGraph pipeline (FastAPI + Postgres checkpoint)     │
 (buyer upload)      │                                                        │
                     │  1. extract_rfp_criteria     (LLM-classified)          │
                     │  2. check_rfp_compliance     (search norms + classify) │
                     │  3. check_prohibited_practices (RFP vs its own rules)  │
                     │  4. checkpoint_a             (pause for human)         │
                     └────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                          React dashboard (buyer reviews,
                          approves/publishes or fixes issues)

  ── built and tested, not yet wired into the graph above ──

  Bid PDFs ────────▶ ingest_bid (Packet-I/II seal) ──▶ Qdrant (`bids` collection)
                              │
                              ▼
              check_document_completeness  (fast presence check)
                              │
                              ▼
              retrieve_and_extract_evidence (per approved criterion)
                              │
                              ▼
              scoring.py — Stage 1 gate → Stage 2 rank (MII → price → MSE match)
                              │
                              ▼
                    ◆ CHECKPOINT B (not built) — evaluator confirms shortlist

  ── read-only, separate from the flow above ──

  Bidder login ───▶ GET /bidder/rfps, GET /bidder/rfps/{id}
                     (published RFPs + required-documents checklist)
```

See `docs/agent-architecture.md` for which of these steps are genuinely agentic (tool choice + judgment that varies with what's discovered) versus fixed pipeline code, and why that distinction matters for an audit trail.

## Tech stack

| Layer | Choice |
|---|---|
| LLM + embeddings | Configurable via `OLLAMA_BASE_URL`/`OLLAMA_LLM_MODEL` — local `llama3.2:3b` or a remote, more capable model (verified with `qwen2.5:7b` on a trusted remote server: faster *and* more accurate on numeric-reasoning cases the local model got wrong). Embeddings: `nomic-embed-text`, 768-dim, unchanged either way. |
| Vector store | Qdrant (Docker) — two collections, `norms` (permanent) and `bids` (per-bidder, Packet-I/II tagged) |
| Metadata / checkpoint store | Postgres (Docker) |
| Orchestration | LangGraph (`PostgresSaver` checkpointer, human-in-the-loop `interrupt()`) |
| Backend API | FastAPI |
| Frontend | React 19 + Vite + Tailwind CSS v4 + Framer Motion |
| Legacy frontend | Streamlit (preserved at `frontend/legacy_streamlit/`, superseded by the React app) |
| Testing | pytest — real unit tests for the scoring engine (the one part of the system with zero LLM/Qdrant dependency) |

Originally chosen for a local-first, no-GPU, 12GB-RAM machine with bidder-data confidentiality in mind (nothing leaves the machine). That confidentiality property is now a deliberate, revisited trade-off, not a given — see [Design notes](#design-notes-worth-knowing).

## Repo structure

```
backend/
├── main.py                          FastAPI app: lifespan (Postgres pool + compiled graph), CORS, routers
├── auth.py                          Role-aware JWT login (buyer + bidder demo credentials — v1 shortcut, see below)
├── logging_config.py                Shared logger -> console + logs/rfp_sentinel.log
├── api/
│   ├── auth.py                       POST /auth/login
│   ├── rfp.py                        Buyer: upload, status, criteria, approve
│   └── bidder.py                     Bidder: GET /bidder/rfps, GET /bidder/rfps/{id}
├── graph/
│   ├── state.py                      LangGraph state shape
│   ├── build_graph.py                extract -> check_compliance -> check_prohibited_practices -> checkpoint_a
│   ├── extract_rfp_criteria.py       PDF -> criteria + required_documents + prohibited_practices
│   ├── check_rfp_compliance.py       criteria vs. the norms knowledge base
│   ├── check_prohibited_practices.py criteria vs. THIS RFP's own listed buyer drafting-mistakes
│   ├── check_document_completeness.py  did the bidder submit the right document TYPES (not yet wired)
│   └── retrieve_and_extract_evidence.py  does bid content satisfy each criterion (not yet wired)
├── llm/ollama_client.py              Generic JSON-mode classifier (text + refs -> verdict + citation), with
│                                      retry-on-network-error and per-call logging
├── scoring/scoring.py                Deterministic Stage 1 gate + Stage 2 rank (MII/price/MSE-match/tie-break),
│                                      zero LLM/Qdrant dependency, unit-tested (not yet wired)
├── rag/                              Qdrant client + embeddings wrapper
└── models/                           rfp.py, evidence.py (Pydantic)

ingestion/                            extract_text, extract_tables, language_filter, chunker, ingest_norms, ingest_bid
data/
├── norms/                            Government norm PDFs + manifest.json (versioning/status)
├── rfps/                             Uploaded RFP PDFs
└── bids/                             Uploaded bid PDFs, Packet-I/II tagged

frontend/
├── src/
│   ├── pages/                         Landing, BuyerLogin/Dashboard, BidderLogin/Dashboard/RfpDetail, ComingSoon (admin stub)
│   └── context/AuthContext.jsx        Token + role, drives routing/gating for both buyer and bidder
└── legacy_streamlit/                  Original Streamlit dashboard, preserved not deleted

docs/
├── agent-architecture.md             What's actually agentic vs. fixed pipeline, and why
├── STATUS_REPORT.md                  Detailed, step-by-step build log and current status
└── diagrams/                          Exported flow diagrams

scripts/                              verify_infra.py, verify_env.py — standalone sanity checks
tests/test_scoring.py                 Real pytest suite for the scoring engine
logs/                                 rfp_sentinel.log (git-ignored) — live progress for any long LLM-heavy run
```

## Local setup

### Prerequisites
- Docker (Desktop or Engine)
- Python 3.11+ with a venv at `./venv`
- Node.js 20+
- [Ollama](https://ollama.com), local or remote — with `llama3.2:3b` (or whatever model you configure) and `nomic-embed-text` pulled:
  ```
  ollama pull llama3.2:3b
  ollama pull nomic-embed-text
  ```

### One-time setup
```
cp .env.example .env
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cd frontend && npm install && cd ..
```

## Running the project

You need **three things running at once**, in separate terminals. Don't run other commands in the backend/frontend terminals while they're up — a stray Ctrl+C or command there will kill the process.

**Terminal 1 — infrastructure:**
```
docker compose up -d
docker ps --format "{{.Names}}: {{.Status}}"    # both containers should say "Up"
systemctl is-active ollama                       # should say "active"; if not: sudo systemctl start ollama
```

**Terminal 2 — backend:**
```
./venv/bin/uvicorn backend.main:app --reload
```
Wait for `Application startup complete`. Health check from any other terminal: `curl http://127.0.0.1:8000/health`

**Terminal 3 — frontend:**
```
cd frontend && npm run dev
```
Wait for the `Local: http://localhost:5173/` line.

**Then:** open **http://localhost:5173**. Buyer flow: log in as buyer, upload an RFP PDF. Bidder flow: log in as bidder, browse published RFPs and their required-documents checklists.

### Authentication

Real accounts now, backed by a Postgres `users` table (`backend/db.py`) with bcrypt-hashed passwords — this replaced the earlier env-var-only shortcut once real seller signup was needed.
- **Buyer**: one demo account, seeded automatically on startup from `BUYER_EMAIL` / `BUYER_PASSWORD` in `.env` (default `buyer@rfpsentinel.local` / `changeme`). Buyer signup isn't built yet — still one account.
- **Bidder**: real self-signup via `POST /auth/signup/bidder` (email, password, org name, and an optional `gem_seller_proof` field). That field is deliberately unvalidated for now — a placeholder for real GeM seller-identity integration later, not a security control; anyone can sign up and enter anything there today.

Still v1-scoped: no email verification, no password reset, no admin account/login yet (see `ROADMAP.md`).

### If something goes wrong mid-evaluation

An RFP evaluation now typically takes **8-15 minutes** (down from an original 15-25 minutes — extraction runs up to 5 LLM questions concurrently, with automatic retry on network errors). Watch it live:
```
tail -f logs/rfp_sentinel.log
```
Every step logs a running "N of Total done" count, so a stall or crash shows exactly where it happened, not just a final printout.
```
ps aux --sort=-%cpu | head -10
```
`ollama`/`llama-server` near the top with high CPU = an evaluation is genuinely running — expected, not a bug. Cross-check against the dashboard's status pill.

To abort an in-progress evaluation:
```
pkill -9 -f "uvicorn backend.main:app"
./venv/bin/uvicorn backend.main:app --reload --host 0.0.0.0
```
Killing the backend stops it from continuing; Ollama itself may stay busy for another 30-90 seconds finishing whatever single request was already in flight before it notices the connection is gone — that's normal, not stuck.

## Design notes worth knowing

- **Criteria extraction is LLM-classified, not regex.** It started as pure keyword regex (a deliberate speed trade-off under time pressure), then moved to LLM classification once a larger remote model was confirmed faster *and* more reliable than the original local one. Regex is still used, but only for the parts that are genuinely deterministic text-extraction problems (pulling out the required-documents list and the RFP's own prohibited-practices list from known layout markers), not for judgment calls.
- **The old deterministic numeric-threshold workaround (`threshold_check.py`) has been removed.** It existed because the original local model reliably got numeric comparisons backwards, even at temperature 0; it was removed after a controlled side-by-side test confirmed the new model gets the same cases right without it.
- **Every flag carries a citation** (norm clause, RFP's own prohibited-practice text, or bid document/page) — an LLM verdict is never surfaced without one. This is the actual validation mechanism in the absence of a labeled ground-truth dataset: every flag is traceable and independently checkable against the real cited text.
- **Data locality is a real, revisited trade-off, not a fixed guarantee.** The original design ran everything on a local, no-GPU machine specifically so bid/RFP content never left the machine. Pointing `OLLAMA_BASE_URL` at a remote server (even a trusted one) reopens that exact question — worth remembering if the remote server's trust status ever changes.
- **Ties and other genuinely ambiguous outcomes are surfaced, not guessed.** A tied L1 price is resolved only by an explicit, buyer-triggered `run_l1_selection()` call (mirroring GeM's own real, documented mechanism, not an invented rule) — and even that function refuses to auto-resolve a price-match decision when a tie has mixed MSE status, since the answer is genuinely undetermined until the tie itself is broken.
- **The Postgres checkpoint only saves progress at step boundaries**, not continuously — killing the backend mid-step loses that step's in-progress work; already-completed steps stay saved but nothing currently auto-resumes an interrupted evaluation.

## Roadmap

See `ROADMAP.md` for what's deliberately deferred — v1.1 (multi-role auth, admin dashboard, bidder self-service upload), v2+ (OCR, multilingual, QCBS), and near-term norm-data follow-ups. It also tracks real procurement edge cases identified during development (arithmetic-discrepancy correction rules, single-bid validity, abnormally-low-bid handling, blacklist/debarment checks) that aren't built yet but are documented so they're not silently missing.
