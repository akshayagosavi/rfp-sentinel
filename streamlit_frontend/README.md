# RFP Sentinel — Streamlit Frontend

## Where this goes in your repo
Put this whole folder at the repo root, e.g. `rfp-sentinel/streamlit_frontend/`
(or rename to `frontend/` if you're replacing the static HTML version — not
both at once, pick one).

```
rfp-sentinel/
  streamlit_frontend/
    Home.py                    <- landing page, run this
    pages/
      1_Evaluator_Desk.py        <- working RFP check + bid evaluation
      2_Admin_Desk.py             <- stub, v1.1
      3_Bidder_Desk.py             <- stub, v1.1
    shared/
      theme.py                    <- CSS + render helpers, one place to edit
      api_client.py                 <- requests wrapper, one place to edit API_BASE / auth
    requirements.txt
```

Streamlit auto-discovers pages inside `pages/` and builds the sidebar nav from
the filenames — the `1_`, `2_`, `3_` prefixes just control the order.

## Run it

1. Install:
   ```
   pip install -r streamlit_frontend/requirements.txt --break-system-packages
   ```
2. Start your FastAPI backend first, from the repo root:
   ```
   uvicorn backend.api.main:app --reload --port 8000
   ```
3. In another terminal, start Streamlit:
   ```
   streamlit run streamlit_frontend/Home.py
   ```
   It opens at `http://localhost:8501`. The sidebar lists all three dashboards.

## Why this structure (same reasoning as the HTML version)
- `shared/theme.py` holds every color/style once — the tricolor bar, letterhead,
  compliance stamp, issue cards. Change the navy shade once, it updates on all
  three dashboard pages.
- `shared/api_client.py` holds the FastAPI calls once. When v1.1 auth exists,
  add the auth header inside `_post()` — every page picks it up automatically.
- Same folder for all three dashboards (not three separate Streamlit apps),
  same reasoning as before: shared backend, shared look, one deployment.

## What's real vs. placeholder
Same as the FastAPI backend itself: file upload → real `extract_text.py` /
`extract_tables.py` / `chunker.py` pipeline. The compliance judgment is a
placeholder rule-engine (`backend/api/compliance_rules.py`) standing in for
the LangGraph/RAG agent — swap that file later, the frontend won't need to
change since the JSON shape stays the same.
