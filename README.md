# RFP Sentinel

**A multi-agent, RAG-based platform that helps government procurement teams draft compliant tenders and evaluate bids fairly, on GeM's Electronics category.**

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-orchestration-1C3C3C)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Qdrant](https://img.shields.io/badge/Qdrant-vector%20DB-DC244C)

<img width="1920" height="935" alt="image" src="https://github.com/user-attachments/assets/c6677a02-f9ad-4b59-8cb5-6d8e3ae86bc3" />
<img width="1920" height="935" alt="image" src="https://github.com/user-attachments/assets/b564e111-460e-4daf-b8b2-9016c4bbf387" />
<img width="1920" height="935" alt="image" src="https://github.com/user-attachments/assets/8c3c932d-399b-45ed-9eeb-8afdc16c7202" />
<img width="1920" height="935" alt="image" src="https://github.com/user-attachments/assets/4b6bdeb2-1fe3-4b24-8724-e1f7fb741acc" />

## Overview

On India's Government e-Marketplace (GeM), a buyer department publishes a tender (RFP), companies submit bids against it, and someone has to check that the tender itself follows procurement rules — then fairly compare every bid against those rules to shortlist a winner. That comparison work is manual, slow, and easy to get wrong or successfully challenge later.

**RFP Sentinel is built for that side of the transaction.** Most AI tooling in this space helps the *bidder* write a better response. RFP Sentinel instead sits with the **buyer / Technical Evaluator**: it checks an RFP against real government procurement norms before it's published, then checks every incoming bid against the RFP's own requirements — producing a ranked, evidence-backed result that a human still has to confirm. Nothing is auto-approved and nothing is auto-rejected; every automated judgment carries a citation back to the rule or clause it's based on.

## Key Features

- **RFP compliance checking before publication** — every extracted eligibility/technical criterion is checked against a government-norms knowledge base (GeM GTC, MSME Public Procurement Policy, GFR 2017 Chapter 6, DPIIT Make in India orders) and against GeM's own list of prohibited buyer drafting practices, so problems surface before the tender goes live, not after.
- **Two human checkpoints, never fully automated** — Checkpoint A lets the buyer review, edit, or justify-and-override any flagged criterion before publishing; Stage 1 evaluation holds any bid with unresolved ("not found") mandatory evidence for a human decision instead of auto-failing it.
- **Deterministic, auditable scoring** — evidence verdicts (pass/fail/partial/not-found) from the LLM are turned into pass/fail gates and rankings by plain, unit-tested Python — not another LLM call — so the same evidence always produces the same result. Supports both **L1** (lowest-price-qualified) and **QCBS** (quality- and cost-based) evaluation methods, with MSE purchase-preference and Make-in-India (Class-I/II local supplier) rules applied automatically.
- **Real two-envelope (sealed) bidding** — a bidder's price document (Packet-II) is stored but never read by the system until Stage 1 technical evaluation is fully complete, mirroring GFR Rule 189.
- **Document-completeness and legitimacy checks** — a fast presence check confirms a bid actually includes every document type the RFP required; a separate bidder-facing check confirms the norms an RFP cites are still `active`, not superseded or withdrawn.
- **Three role-based dashboards** — Buyer (draft, review, publish, resolve, rank), Bidder (browse, apply, track), and Admin (manage the norm knowledge base's active/superseded status, activate/deactivate accounts, audit any RFP published despite an unresolved flag).
- **Real session revocation** — deactivating a user blocks their next authenticated request immediately, even if their JWT hasn't expired yet.

## Architecture

The evaluation pipeline runs in two phases, orchestrated with **LangGraph** and checkpointed to **Postgres** so long-running, LLM-heavy steps can pause for human input and resume exactly where they left off:

**Phase 1 — RFP intake** (`extract_rfp_criteria → check_rfp_compliance → check_prohibited_practices → checkpoint_a`): an uploaded tender PDF is parsed into structured criteria, each criterion is checked against the norms knowledge base and GeM's prohibited-practices list, then the buyer reviews the result at **Checkpoint A** — editing, overriding with recorded reasoning, or publishing as-is.

**Phase 2 — Bid evaluation**, triggered per RFP once bidding closes (by a closing-date timer or a manual override): each bid's technical documents are matched against the buyer-approved criteria and scored (`score_stage1`) to produce a pass/fail gate and technical score. Once the buyer explicitly opens financial bids, Stage 2 extracts each qualifying bid's sealed price and ranks the field (`score_stage2` / `score_stage2_qcbs`).

Retrieval is filtered at query time — norm search only ever sees `status=active` clauses, and bid search is hard-isolated per `bid_id` and per packet (technical vs. sealed financial) — so neither a superseded rule nor another bidder's document can leak into a result.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI, Uvicorn |
| Orchestration | LangGraph + `langgraph-checkpoint-postgres` |
| LLM inference | Ollama (remote or local) — classification/generation and RFP summaries |
| Embeddings | Ollama — `bge-m3` |
| Vector store | Qdrant (separate `norms` and `bids` collections) |
| Relational store | PostgreSQL (users, RFPs, bids, evidence — plus LangGraph's own checkpoint tables) |
| Document parsing | pdfplumber (text + table extraction) |
| Auth | JWT (PyJWT, HS256) + bcrypt password hashing, role-based (buyer/bidder/admin) |
| Frontend | React 19, Vite, Tailwind CSS v4, React Router, Framer Motion, Axios |

## Getting Started

### Prerequisites

- Docker (for Postgres + Qdrant)
- Python 3.11+
- Node.js 20+
- [Ollama](https://ollama.com), reachable locally or over the network, with an LLM model and an embedding model pulled — this repo defaults to `qwen2.5:7b` and `bge-m3`:
  ```
  ollama pull qwen2.5:7b
  ollama pull bge-m3
  ```

### Setup

```bash
cp .env.example .env               # edit if your Ollama host/models or ports differ

python3 -m venv venv
./venv/bin/pip install -r requirements.txt

cd frontend && npm install && cd ..
```

### Run

In three separate terminals, from the repo root:

```bash
docker compose up -d                            # Postgres + Qdrant
```
```bash
./venv/bin/uvicorn backend.main:app --reload    # backend — wait for "Application startup 
./venv/bin/uvicorn backend.main:app --reload --host 0.0.0.0
complete"
```
```bash
cd frontend && npm run dev                      # frontend — http://localhost:5173
```

Optional sanity checks before your first run:
```bash
./venv/bin/python -m scripts.verify_infra   # confirms Postgres + Qdrant are actually reachable
./venv/bin/python -m scripts.verify_env     # confirms Ollama is reachable and both models respond
```

Once the backend is up, ingest the norm knowledge base (only needed once, or after adding/changing a document in `data/norms/`):
```bash
./venv/bin/python -m ingestion.ingest_norms
```

## Usage

1. **Buyer** signs in and uploads a tender PDF, which is parsed and checked in the background. Anything flagged — a norm conflict or a match against GeM's prohibited-practices list — is shown inline with its citation at Checkpoint A; the buyer edits, overrides with a written reason, or publishes as-is.
2. **Bidders** browse published tenders without logging in, and can pull up a plain-language summary and a legitimacy check (are the norms this RFP cites still active?) before deciding to apply. Applying requires an account; MSE/MII status is declared once on the bidder's profile with a supporting certificate, then applied automatically to every bid.
3. Once the tender's closing date passes (or the buyer closes it manually from the RFP's own management page), Stage 1 technical evaluation runs automatically across all submitted bids. The buyer resolves any mandatory criterion the model couldn't find evidence for either way, then opens financial bids to trigger Stage 2 ranking.
4. **Admin** manages the norm knowledge base's status (active/superseded/withdrawn), activates or deactivates user accounts, and audits any RFP that was published with a flag still unresolved.

## Project Structure

```
backend/
  api/            # FastAPI routers: auth, rfp (buyer), bidder, bids (public), admin
  graph/          # LangGraph nodes + the deterministic Stage 1/2 evaluation runners
  scoring/        # Pure-Python scoring engine (zero LLM/Qdrant dependency)
  rag/            # Qdrant client + Ollama embeddings wrapper
  llm/            # Ollama classification client (JSON-mode, retry, citation-grounded)
  models/         # Pydantic schemas (RFP/criteria, evidence)
  auth.py, db.py  # JWT/bcrypt auth, Postgres schema + queries
  main.py         # App entrypoint — lifespan startup, routers, closing-date timer

frontend/
  src/pages/      # Landing, Buyer/Bidder/Admin dashboards, login/signup, bid browsing
  src/components/ # Shared UI (nav, forms, evaluation-result views, KPI cards)
  src/api/        # Axios client

ingestion/        # PDF text/table extraction, language filtering, chunking, norm ingestion CLI
scripts/          # Environment/infra verification, ad-hoc norm-retrieval query tool
data/norms/       # Source norm PDFs + manifest.json (name, status, version per document)
tests/            # pytest suite (currently: scoring engine)
docker-compose.yml
requirements.txt
```

## Configuration

All configuration lives in `.env` (copy from `.env.example`):

| Variable | Purpose |
|---|---|
| `QDRANT_URL` | Qdrant endpoint |
| `POSTGRES_URL` | Postgres connection string (metadata store + LangGraph checkpoints) |
| `OLLAMA_BASE_URL` | Ollama host for LLM generation/classification |
| `OLLAMA_LLM_MODEL` | Model used for compliance checks, evidence classification, and summaries |
| `OLLAMA_EMBED_MODEL` | Model used for norm/bid embeddings |
| `AUTH_SECRET_KEY` | JWT signing secret — change this before any real deployment |
| `BUYER_EMAIL` / `BUYER_PASSWORD` | Seeds one demo buyer account on startup |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Seeds one demo admin account on startup |

Bidder accounts aren't seeded — they sign up for real via the app.
