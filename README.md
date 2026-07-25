# RFP Sentinel

A RAG-based bid-evaluation co-pilot for GeM (Government e-Marketplace) procurement, scoped to the **Electronics category**. Its core differentiator is the **buyer/evaluator side** of government procurement — every commercial RFP-AI tool on the market serves bidders responding to tenders; this is the other side of that transaction, a gap in the market. On top of that, it's grown into a full three-role platform: buyers publish and evaluate RFPs, bidders browse and submit against them, and admins manage the norm knowledge base, user accounts, and buyer-conduct oversight.

<img width="1920" height="925" alt="image" src="https://github.com/user-attachments/assets/67c1c3d5-fa5d-4ad4-abef-d9c7a15bff84" />
<img width="1920" height="925" alt="image" src="https://github.com/user-attachments/assets/1c7aa3a2-8ec6-42e9-9060-bbd0ad67d606" />
<img width="1920" height="925" alt="image" src="https://github.com/user-attachments/assets/7067c59d-22d3-4514-a54a-95d8f30c4e5d" />
<img width="1920" height="925" alt="Screenshot from 2026-07-21 23-44-49" src="https://github.com/user-attachments/assets/eff4c7bf-ad7a-4f69-8262-173019011d2d" />

A buyer uploads an RFP/tender PDF. The system extracts its requirements, checks them against a knowledge base of real government procurement norms (GeM's GTC, the MSME Public Procurement Policy, GFR 2017, DPIIT Make-in-India orders, MeitY's CRS handbook), separately checks the RFP against **its own** listed buyer drafting-mistakes, flags anything that conflicts with a citation, and pauses for a human to review (with a mandatory, server-enforced justification for publishing anyway) before anything goes live. Bidders browse and apply publicly, submit documents under a blocking completeness check, and get a sealed financial bid (Packet-II never opened until the technical gate closes). Once the RFP closes — automatically on its deadline, or on a buyer's manual override — Stage 1 checks every bid's technical documents against the approved criteria and gates pass/fail; Stage 2 (triggered separately, mirroring the real two-envelope principle) reads sealed prices and ranks by L1 or QCBS, with MSE purchase-preference price-matching and GeM's own documented tie-break mechanism, all with numbers read from the RFP's own text, not manually supplied. Admins control the norm knowledge base's active/superseded/withdrawn status, manage user accounts (with real session revocation, not just login-blocking), and audit every RFP a buyer published despite a flagged clause.

## Current status (v1 — feature-complete, ~97%)

**Buyer side — fully working end-to-end:**
- RFP PDF upload → criteria extraction (LLM-classified: guidance-vs-criterion, mandatory/optional, technical/financial/eligibility/other) → compliance check against the norms knowledge base → a **second, separate self-check** of the RFP's own criteria against GeM's own listed "buyer prohibited practices" → human checkpoint (Checkpoint A) with override-and-reasoning, **enforced server-side, not just by the UI** → publish.
- `evaluation_method` (L1/QCBS) and MSE purchase-preference numbers (price band %, quantity share %) are extracted directly from the RFP's own text, not assumed defaults.
- A closing-date timer (60s-granularity background poll) auto-closes submissions and kicks off Stage 1 evaluation; a buyer can also trigger "Close & Evaluate Now" manually, for demos or genuinely early closes.
- Once Stage 1 finishes, a **buyer must resolve every mandatory criterion left `not_found`** (with recorded reasoning) before "Open Financial Bids" is allowed — a bid can't reach financial ranking with open technical questions.
- "Open Financial Bids" is a separate, explicit action from closing — mirrors the real two-envelope principle that a technically disqualified bidder's price is never even opened.
- Stage 2 ranks by L1 (price-ascending, with MSE price-match + GeM's own documented tie-break mechanism) or QCBS (technical score blended with price, per the RFP's own weighting if stated).

**Bid evaluation — fully wired, not just individually tested:**
- Bid ingestion with a structural technical/financial (Packet-I/Packet-II) seal — `search_bid()` defaults to Packet-I, so a caller that forgets to specify a packet can never see pricing data.
- A fast document-completeness checklist enforced as a **hard block at submission time** — a bidder cannot submit without every required document type present.
- Evidence extraction — does the bidder's content actually satisfy each approved criterion, with citations. A mandatory criterion's `partial` verdict is treated as a fail (no partial credit on a "must/shall" requirement, matching GeM's own binary technical gate); `not_found` is held for human review, never auto-failed.
- A deterministic scoring engine (Stage 1 pass/fail gate, Stage 2 MII-filter → price-rank → MSE price-match, or QCBS blend) — zero LLM/Qdrant dependency in the scoring math itself, real pytest suite (26 tests).
- Price is read from the bidder's sealed financial document by an LLM call at Stage 2, not collected as a form field at submission — verified against real currency-formatted text, exact match every time tested.

**Bidder-facing:** public browsing (no login needed, matching real GeM), self-signup, profile with MSE/MII certificate upload (seller-level, declared once — not re-asked per bid), document submission under the completeness gate, "My Bids" status tracking, a plain-language RFP summary (LLM-generated, cached), and a legitimacy check confirming the norms an RFP cites are still active.

**Admin dashboard — all three planned capabilities built:**
1. **Norm knowledge-base management** — flip a norm active/superseded/withdrawn; every future compliance check and evidence search respects it immediately.
2. **User management** — deactivate/reactivate any account. Deactivation is checked on **every authenticated request**, not just at login, so an already-issued JWT is revoked immediately — not just blocked from a future login.
3. **Buyer-conduct oversight** — every published RFP with a flagged criterion, and whether the buyer recorded a reason for publishing anyway. Building this surfaced a real gap (server-side approval had no check for this at all, only the UI enforced it) — now fixed.

**Not yet built (deliberately tracked, not overlooked):** QCBS's default weighting has never been validated against a real QCBS RFP (none exists in the data gathered so far — every real RFP seen uses L1). See `ROADMAP.md`.

## Architecture

```
                     ┌─────────────────────┐
  Norm PDFs  ──────▶ │  Ingestion pipeline  │ ──▶ Qdrant (`norms` collection)
 (GTC, MSME, GFR,    │  extract → chunk →   │     — the permanent rulebook,
  MII orders, CRS)   │  embed → store       │       admin-controlled status
                     └─────────────────────┘

                     ┌────────────────────────────────────────────────────────┐
  RFP PDF   ───────▶ │ LangGraph pipeline (FastAPI + Postgres checkpoint)     │
 (buyer upload)      │                                                        │
                     │  1. extract_rfp_criteria   (LLM-classified; also pulls │
                     │     evaluation_method, MSE price-band %/share %)       │
                     │  2. check_rfp_compliance     (search norms + classify) │
                     │  3. check_prohibited_practices (RFP vs its own rules)  │
                     │  4. checkpoint_a  (pause for human; server enforces    │
                     │     override_reasoning on every flagged criterion)    │
                     └────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                          React dashboard (buyer reviews,
                          approves/publishes or fixes issues)
                                        │
                                        ▼
                    Public bid listing/detail — anyone can browse and Apply
                                        │
                                        ▼
              Bidder submits (Packet-I/II seal, completeness gate blocks
              an incomplete submission at upload time)
                                        │
                                        ▼
        closing_date timer OR buyer's manual "Close & Evaluate Now"
                                        │
                                        ▼
              run_stage1_evaluation — evidence extraction per approved
              criterion, deterministic pass/fail gate (mandatory partial=fail)
                                        │
                                        ▼
        ◆ Buyer resolves any `not_found` mandatory criterion (required
          before financial bids can open — this is enforced, not optional)
                                        │
                                        ▼
              buyer's "Open Financial Bids" (separate, explicit action)
                                        │
                                        ▼
              run_stage2_evaluation — price extracted from sealed Packet-II,
              L1 rank + MSE price-match, or QCBS blend, per the RFP's own
              evaluation_method
                                        │
                                        ▼
              ◆ Buyer resolves an L1 tie via run_l1_selection() (GeM's own
                documented random-draw mechanism, MSE-priority-aware)
                                        │
                                        ▼
                          Final ranking, full audit trail

  ── separate surfaces ──

  Bidder: public browsing, self-signup, profile (MSE/MII certs), submission,
          My Bids, RFP summary + legitimacy check

  Admin:  norm status control, user management (deactivate = revoked
          immediately, not just blocked at next login), buyer-conduct
          oversight (flagged-but-unjustified published RFPs)
```

See `docs/agent-architecture.md` for which of these steps are genuinely agentic (tool choice + judgment that varies with what's discovered) versus fixed pipeline code, and why that distinction matters for an audit trail.

## Tech stack

| Layer | Choice |
|---|---|
| LLM + embeddings | Configurable via `OLLAMA_BASE_URL`/`OLLAMA_LLM_MODEL` — local `llama3.2:3b` or a remote, more capable model (verified with `qwen2.5:7b` on a trusted remote server: faster *and* more accurate on numeric-reasoning cases the local model got wrong). Embeddings: `nomic-embed-text`, 768-dim, unchanged either way. |
| Vector store | Qdrant (Docker) — two collections, `norms` (permanent, admin-controlled status) and `bids` (per-bidder, Packet-I/II tagged) |
| Metadata / checkpoint store | Postgres (Docker) — `users`, `rfps`, `bids`, `bid_evidence` tables plus LangGraph's own checkpoint tables, same pool |
| Orchestration | LangGraph (`PostgresSaver` checkpointer, human-in-the-loop `interrupt()`) for the RFP-upload-through-Checkpoint-A flow; plain async functions + FastAPI `BackgroundTasks` for Stage 1/2 evaluation (no human-pause mid-step needed there beyond the resolve/open-financial-bids gates, which are just separate endpoints) |
| Backend API | FastAPI |
| Frontend | React 19 + Vite + Tailwind CSS v4 + Framer Motion |
| Legacy frontend | Streamlit (preserved at `frontend/legacy_streamlit/`, superseded by the React app) |
| Testing | pytest — real unit tests for the scoring engine (26 tests, the one part of the system with zero LLM/Qdrant dependency) |

Originally chosen for a local-first, no-GPU, 12GB-RAM machine with bidder-data confidentiality in mind (nothing leaves the machine). That confidentiality property is now a deliberate, revisited trade-off, not a given — see [Design notes](#design-notes-worth-knowing).

## Repo structure

```
backend/
├── main.py                          FastAPI app: lifespan (Postgres pool + compiled graph), CORS, routers,
│                                      the closing-date timer background loop
├── auth.py                          Role-aware JWT auth -- get_current_buyer/bidder/admin/user_email all
│                                      check users.is_active on every request, not just at login
├── db.py                            Postgres metadata layer: users, rfps, bids, bid_evidence -- signup,
│                                      publish, close/evaluate, evidence resolution, stage2 results,
│                                      user deactivation, RFP summary cache
├── logging_config.py                Shared logger -> console + logs/rfp_sentinel.log
├── api/
│   ├── auth.py                       login, bidder signup, /me, MSE/MII certificate upload
│   ├── rfp.py                        Buyer: upload, criteria, approve, close, open-financial-bids,
│   │                                  evidence resolution, run-l1-selection, list own RFPs
│   ├── bidder.py                     Bidder: submit (completeness-gated), my-bids
│   ├── bids.py                       Public: browse/detail/document, legitimacy-check, summary
│   └── admin.py                      Admin: norm status, user list/deactivate, flagged-RFP oversight
├── graph/
│   ├── state.py                      LangGraph state shape
│   ├── build_graph.py                extract -> check_compliance -> check_prohibited_practices -> checkpoint_a
│   ├── extract_rfp_criteria.py       PDF -> criteria + required_documents + prohibited_practices +
│   │                                  evaluation_method + MSE price-band %/share %
│   ├── check_rfp_compliance.py       criteria vs. the norms knowledge base
│   ├── check_prohibited_practices.py criteria vs. THIS RFP's own listed buyer drafting-mistakes
│   ├── check_document_completeness.py did the bidder submit the right document TYPES
│   ├── retrieve_and_extract_evidence.py does bid content satisfy each criterion
│   ├── run_stage1_evaluation.py      orchestrates evidence extraction + scoring across all bids on an RFP
│   ├── extract_bid_price.py          reads a total price out of the bidder's sealed financial document
│   ├── run_stage2_evaluation.py      orchestrates price extraction + L1/QCBS ranking
│   ├── check_rfp_legitimacy.py       bidder-facing: are this RFP's cited norms still active
│   └── generate_rfp_summary.py       bidder-facing: plain-language RFP summary (LLM, cached)
├── llm/ollama_client.py              Generic JSON-mode classifier (text + refs -> verdict + citation), with
│                                      retry-on-network-error and per-call logging
├── scoring/scoring.py                Deterministic Stage 1 gate + Stage 2 rank (L1: MII/price/MSE-match/
│                                      tie-break; QCBS: technical+price blend) -- zero LLM/Qdrant
│                                      dependency, unit-tested
├── rag/                              Qdrant client + embeddings wrapper; list_norms() backs admin UI
└── models/                           rfp.py, evidence.py (Pydantic)

ingestion/                            extract_text, extract_tables, language_filter, chunker, ingest_norms, ingest_bid
data/
├── norms/                            Government norm PDFs + manifest.json (versioning/status)
├── rfps/                             Uploaded RFP PDFs
├── bids/                             Uploaded bid PDFs, Packet-I/II tagged, per bid_id folder
└── certificates/                     MSE/MII certificate uploads, per user

frontend/
├── src/
│   ├── pages/                         Landing, Bids/BidDetail (public), Buyer{Login,Dashboard,Rfps},
│   │                                  RfpManage (close/evaluate/open-financial-bids/tie-break UI),
│   │                                  Bidder{Login,Signup,Dashboard}, BidSubmission, Profile,
│   │                                  Admin{Login,Dashboard}
│   ├── components/                    Nav (owns the auth-menu logic for every page), Container (one
│   │                                  width/spacing system reused everywhere -- ~90% viewport, capped
│   │                                  at 1280px), Footer (full on public pages, slim on dashboards),
│   │                                  KpiStrip/KpiCard (the 4-up metric row at the top of every
│   │                                  dashboard, honest real counts, never fabricated numbers)
│   └── context/AuthContext.jsx        Token + role, drives routing/gating for all three roles
└── legacy_streamlit/                  Original Streamlit dashboard, preserved not deleted

docs/
├── agent-architecture.md             What's actually agentic vs. fixed pipeline, and why
├── STATUS_REPORT.md                  Detailed, step-by-step build log and current status
└── diagrams/                          Exported flow diagrams

scripts/                              verify_infra.py, verify_env.py — standalone sanity checks
tests/test_scoring.py                 Real pytest suite for the scoring engine (26 tests)
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

**Then:** open **http://localhost:5173**.
- **Anyone** (no login): browse published bids, view detail, generate a plain-language summary, check citation freshness.
- **Buyer**: log in, upload an RFP PDF, review/approve at Checkpoint A, close/evaluate, resolve any pending criteria, open financial bids, resolve an L1 tie if one comes up.
- **Bidder**: sign up, set up MSE/MII certificates in Profile if applicable, browse bids, Apply, submit documents + a sealed financial document, track status in My Bids.
- **Admin**: log in at `/admin/login`, manage norm status, manage user accounts, review buyer-conduct oversight.

### Testing from another device on the same network

The frontend already listens on every network interface (`server.host: true` in `vite.config.js`), so a teammate can load `http://<your-LAN-IP>:5173` and the page itself will render fine. **But the plain `uvicorn backend.main:app --reload` command above only binds to `127.0.0.1`** — reachable from your machine only. Anyone else's login (or any other API call) will silently fail to connect, not because of wrong credentials, but because their request can never reach the backend at all. Confirm what's actually bound with `ss -tlnp | grep -E ":8000|:5173"` — if port 8000 shows `127.0.0.1` instead of `*`/`0.0.0.0`, that's why. Fix: add `--host 0.0.0.0` —
```
./venv/bin/uvicorn backend.main:app --reload --host 0.0.0.0
```

### Authentication

Real accounts backed by a Postgres `users` table (`backend/db.py`) with bcrypt-hashed passwords.
- **Buyer**: one demo account, seeded automatically on startup from `BUYER_EMAIL` / `BUYER_PASSWORD` in `.env` (default `buyer@rfpsentinel.local` / `changeme`).
- **Admin**: one demo account, seeded from `ADMIN_EMAIL` / `ADMIN_PASSWORD` (default `admin@rfpsentinel.local` / `changeme`). No admin self-signup — an admin account is provisioned, not created on request.
- **Bidder**: real self-signup via `POST /auth/signup/bidder` (email, password, org name, and an optional `gem_seller_proof` field). That field is deliberately unvalidated for now — a placeholder for real GeM seller-identity integration later, not a security control.

**Deactivation is real, not cosmetic**: an admin deactivating a user blocks their next login *and* immediately invalidates any JWT they're already holding — every authenticated request checks `users.is_active` fresh, not just the login endpoint. Reactivating restores access instantly, same token included, no re-login needed.

Still not built: email verification, password reset (see `ROADMAP.md`).

### If something goes wrong mid-evaluation

An RFP evaluation now typically takes **8-15 minutes** for Checkpoint A extraction (down from an original 15-25 minutes — extraction runs up to 5 LLM questions concurrently, with automatic retry on network errors). Stage 1/2 evaluation time scales with criteria count and bidder count, but each individual step is fast (a few seconds). Watch any of it live:
```
tail -f logs/rfp_sentinel.log
```
Every step logs a running "N of Total done" count, so a stall or crash shows exactly where it happened, not just a final printout.
```
ps aux --sort=-%cpu | head -10
```
`ollama`/`llama-server` near the top with high CPU = an evaluation is genuinely running — expected, not a bug.

To abort an in-progress evaluation:
```
pkill -9 -f "uvicorn backend.main:app"
./venv/bin/uvicorn backend.main:app --reload --host 0.0.0.0
```
Killing the backend stops it from continuing; Ollama itself may stay busy for another 30-90 seconds finishing whatever single request was already in flight before it notices the connection is gone — that's normal, not stuck.

## Design notes worth knowing

- **Criteria extraction is LLM-classified, not regex.** It started as pure keyword regex (a deliberate speed trade-off under time pressure), then moved to LLM classification once a larger remote model was confirmed faster *and* more reliable than the original local one. Regex is still used, but only for genuinely deterministic text-extraction problems (required-documents list, prohibited-practices list, `evaluation_method`, MSE price-band %/share % — all pulled from known layout markers or a standard GeM boilerplate paragraph, verified against real RFP text before being trusted), not for judgment calls.
- **Mandatory criteria are a binary gate, not a scored one.** GeM's own technical evaluation gives no partial credit on a "must/shall" requirement — a `partial` verdict on a mandatory criterion fails the bidder exactly like an outright `fail`. This is different from a non-mandatory ("preferred") criterion, where `partial` earns half credit in `technical_score` rather than disqualifying anyone.
- **A `not_found` mandatory criterion blocks Stage 2 until a human resolves it.** Found via the admin buyer-conduct oversight screen's real-world testing that a bid could otherwise reach financial ranking with unresolved technical questions — now enforced server-side (`POST /rfp/{id}/bids/{bid_id}/evidence/{criterion_id}/resolve`, required reasoning, same audit-trail discipline as Checkpoint A's overrides).
- **Every flag carries a citation** (norm clause, RFP's own prohibited-practice text, or bid document/page) — an LLM verdict is never surfaced without one. This is the actual validation mechanism in the absence of a labeled ground-truth dataset: every flag is traceable and independently checkable against the real cited text.
- **A flagged criterion can't be published without recorded reasoning — enforced by the backend, not just the UI.** The frontend's publish-with-overrides flow always required this, but the API itself didn't check until a live audit-screen test surfaced a real bypass (anyone calling the API directly could skip it). Fixed once found, not after a real incident.
- **Financial bids are documents, not form fields.** A bidder uploads a sealed price-schedule PDF; the actual number is read by an LLM only when a buyer explicitly "opens financial bids," after the technical gate has closed — matching real GFR Rule 189 sealed-bid practice more closely than a number sitting unsealed in the database from the moment of submission.
- **MSE/MII status is declared once, at the account level, not per bid.** Matches how GeM itself treats these as seller-registration attributes, verified once — not re-asked on every submission. Snapshotted onto the bid at submission time for audit purposes.
- **Data locality is a real, revisited trade-off, not a fixed guarantee.** The original design ran everything on a local, no-GPU machine specifically so bid/RFP content never left the machine. Pointing `OLLAMA_BASE_URL` at a remote server (even a trusted one) reopens that exact question — worth remembering if the remote server's trust status ever changes.
- **Ties and other genuinely ambiguous outcomes are surfaced, not guessed.** A tied L1 price is resolved only by an explicit, buyer-triggered `run_l1_selection()` call (mirroring GeM's own real, documented mechanism, not an invented rule) — and even that function refuses to auto-resolve a price-match decision when a tie has mixed MSE status, since the answer is genuinely undetermined until the tie itself is broken.
- **The Postgres checkpoint only saves progress at step boundaries**, not continuously — killing the backend mid-step loses that step's in-progress work; already-completed steps stay saved but nothing currently auto-resumes an interrupted evaluation.
- **One shared design system across every page, not per-page styling.** `Container`/`Footer`/`KpiStrip` (`frontend/src/components/`) are reused by every public page and all three dashboards — same width (~90% of viewport, capped at 1280px), same card radius/spacing, same KPI-card look. The admin dashboard specifically moved from three long stacked sections to a tabbed layout (Norms / Users / Buyer Conduct) once it became clear a single continuous scroll doesn't hold up once every capability is actually built out.
- **KPI numbers are real counts wherever the data exists, not decoration.** Each dashboard's metric strip is computed from data already returned by existing endpoints (e.g. a buyer's "Flagged criteria" count comes from actually fetching each of their RFP's criteria and counting real flags) — not a fabricated number picked to look full. Where a true live count genuinely isn't available without a backend change (e.g. a public-page norm count), the choice was to either reuse a different public endpoint honestly or fall back to qualitative copy, never invent a figure.

## Roadmap

See `ROADMAP.md` for what's deliberately deferred — v2+ items (OCR, multilingual, a real QCBS validation once a real QCBS RFP is found), and near-term norm-data follow-ups. It also tracks real procurement edge cases identified during development (arithmetic-discrepancy correction rules, single-bid validity, abnormally-low-bid handling, blacklist/debarment checks) that aren't built yet but are documented so they're not silently missing.
