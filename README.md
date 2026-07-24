# RFP Sentinel

A RAG-based bid-evaluation co-pilot for GeM (Government e-Marketplace) Technical Evaluators, scoped to the **Electronics category**. It serves the **buyer/evaluator side** of government procurement — every commercial RFP-AI tool on the market serves bidders responding to tenders; this is the other side of that transaction, a gap in the market.

<img width="1920" height="925" alt="image" src="https://github.com/user-attachments/assets/67c1c3d5-fa5d-4ad4-abef-d9c7a15bff84" />
<img width="1920" height="925" alt="image" src="https://github.com/user-attachments/assets/1c7aa3a2-8ec6-42e9-9060-bbd0ad67d606" />
<img width="1920" height="925" alt="image" src="https://github.com/user-attachments/assets/7067c59d-22d3-4514-a54a-95d8f30c4e5d" />
<img width="1920" height="925" alt="Screenshot from 2026-07-21 23-44-49" src="https://github.com/user-attachments/assets/eff4c7bf-ad7a-4f69-8262-173019011d2d" />


A buyer uploads an RFP/tender PDF. The system extracts its requirements, checks them against a knowledge base of real government procurement norms (GeM's General Terms & Conditions, the MSME Public Procurement Policy, MeitY's CRS handbook), flags anything that conflicts with those norms with a citation, and pauses for a human to review before anything is published.

## Current status (v1, in progress)

**Built and working end-to-end today:**
- Norm-document ingestion → Qdrant knowledge base (3 real government documents, ~728 chunks)
- RFP PDF upload → criteria extraction → compliance check against norms → human checkpoint → publish
- A React dashboard (buyer role only) wired to a FastAPI backend, with LangGraph orchestrating the pipeline and Postgres as its checkpoint store
- Minimal JWT login (single hardcoded demo credential — see [Authentication](#authentication-v1-shortcut) below)

**Not yet built** (see `ROADMAP.md` for the full list):
- Bidder-side upload and bid-vs-criteria evaluation (the scoring/shortlist half of the pipeline)
- Admin dashboard, multi-user auth, bidder dashboard
- LLM-based criteria extraction (current extraction is rule-based — see [Design notes](#design-notes-worth-knowing))

## Architecture

```
                     ┌─────────────────────┐
  Norm PDFs  ──────▶ │  Ingestion pipeline  │ ──▶ Qdrant (`norms` collection)
 (GTC, MSME,         │  extract → chunk →   │     — the permanent rulebook,
  CRS handbook)      │  embed → store       │       built once, ahead of time
                     └─────────────────────┘

                     ┌──────────────────────────────────────────────┐
  RFP PDF   ───────▶ │ LangGraph pipeline (FastAPI + Postgres ckpt) │
 (buyer upload)      │                                              │
                     │  1. extract_rfp_criteria   (rule-based)      │
                     │  2. check_rfp_compliance   (real agent —     │
                     │     search Qdrant + threshold-check or LLM)  │
                     │  3. checkpoint_a           (pause for human) │
                     └──────────────────────────────────────────────┘
                                        │
                                        ▼
                          React dashboard (buyer reviews,
                          approves/publishes or fixes issues)
```

See `docs/agent-architecture.md` for a detailed breakdown of what's actually agentic here (one real agent today) versus fixed pipeline code, and why.

## Tech stack

| Layer | Choice |
|---|---|
| LLM + embeddings | Llama 3.2 3B + nomic-embed-text, via Ollama (local, CPU-only) |
| Vector store | Qdrant (Docker) |
| Metadata / checkpoint store | Postgres (Docker) |
| Orchestration | LangGraph (`PostgresSaver` checkpointer, human-in-the-loop `interrupt()`) |
| Backend API | FastAPI |
| Frontend | React 19 + Vite + Tailwind CSS v4 + Framer Motion |
| Legacy frontend | Streamlit (preserved at `frontend/legacy_streamlit/`, superseded by the React app) |

Chosen for a local-first, no-GPU, 12GB-RAM machine, with bidder-data confidentiality in mind (nothing leaves the machine).

## Repo structure

```
backend/
├── main.py                  FastAPI app: lifespan (Postgres pool + compiled graph), CORS, routers
├── auth.py                  Minimal JWT login (v1 shortcut, see below)
├── api/
│   ├── auth.py               POST /auth/login
│   └── rfp.py                POST /rfp/upload, GET .../status, GET .../criteria, POST .../criteria/approve
├── graph/
│   ├── state.py              LangGraph state shape
│   ├── build_graph.py        extract → check_compliance → checkpoint_a
│   ├── extract_rfp_criteria.py
│   └── check_rfp_compliance.py
├── llm/ollama_client.py       Generic JSON-mode classifier (text + retrieved refs → verdict + citation)
├── scoring/threshold_check.py Deterministic number-threshold checker (LLM is unreliable at this — see docs)
├── rag/                       Qdrant client + embeddings wrapper
└── models/rfp.py               Criterion / StructuredRFP (Pydantic)

ingestion/                     extract_text, extract_tables, language_filter, chunker, ingest_norms
data/
├── norms/                     Government norm PDFs + manifest.json (versioning/status)
├── rfps/                      Uploaded RFP PDFs
└── bids/                      (not yet used — bidder upload not built)

frontend/
├── src/                        React app: Landing, BuyerLogin, BuyerDashboard, ComingSoon (bidder/admin stubs)
└── legacy_streamlit/           Original Streamlit dashboard, preserved not deleted

docs/
├── agent-architecture.md      What's actually agentic vs. fixed pipeline, and why
└── diagrams/                   Exported flow diagrams

scripts/                        verify_infra.py, verify_env.py, query_norms.py — standalone sanity checks
tests/                          Scaffolded, not yet populated with real test cases
```

## Local setup

### Prerequisites
- Docker (Desktop or Engine)
- Python 3.11+ with a venv at `./venv`
- Node.js 20+
- [Ollama](https://ollama.com) installed, with `llama3.2:3b` and `nomic-embed-text` pulled:
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

**Then:** open **http://localhost:5173**, log in, upload an RFP PDF.

### Authentication (v1 shortcut)

Default demo login: `buyer@rfpsentinel.local` / `changeme` (set via `BUYER_EMAIL` / `BUYER_PASSWORD` in `.env`). This is a single hardcoded credential with a real JWT issued on login — no password hashing, no `users` table. Deliberate, documented v1 scope-cut, not a hidden gap; real multi-user auth is v1.1 (see `ROADMAP.md`).

### If something goes wrong mid-evaluation

An RFP evaluation can take **15-25 minutes** on CPU-only hardware (roughly 20-40 seconds per criterion through the LLM). To check if something's actually happening:
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

- **Criteria extraction is rule-based, not LLM-based.** Mandatory/optional and category (financial/eligibility) are decided by keyword regex, not a model call — a deliberate speed/reliability trade-off under time pressure, not an oversight. See `docs/agent-architecture.md`.
- **Numeric compliance checks are deterministic, not LLM-judged.** Testing found the LLM reliably identifies the right numbers in a threshold comparison but consistently draws the wrong conclusion from them, even at temperature 0. Plain comparisons are now handled by `threshold_check.py`; the LLM is only used for genuinely qualitative judgment.
- **Every compliance flag carries a citation** (norm name, clause, page) — an LLM verdict is never surfaced without one. This is the actual validation mechanism in the absence of a labeled ground-truth dataset: every flag is traceable and independently checkable against the real cited text.
- **The Postgres checkpoint only saves progress at step boundaries**, not continuously — killing the backend mid-step loses that step's in-progress work; already-completed steps stay saved but nothing currently auto-resumes an interrupted evaluation.

## Roadmap

See `ROADMAP.md` for what's deliberately deferred — v1.1 (multi-role auth, bidder/admin dashboards, bidder self-service upload), v2+ (OCR, multilingual, parallel evidence extraction), and near-term norm-data follow-ups.
