import streamlit as st

from shared.theme import inject_theme, render_letterhead
from shared.api_client import health_check, API_BASE

st.set_page_config(page_title="RFP Sentinel", page_icon="🛡️", layout="centered")
inject_theme()
render_letterhead("Procurement Compliance Desk")

st.markdown("### Select a Dashboard")
st.caption("No login yet (v1.1 will add role-based auth) — use the sidebar, or the links below.")

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("**Buyer**")
    st.caption("Check a draft RFP against norms, or evaluate a bid against an RFP.")
    st.page_link("pages/1_Buyer_Desk.py", label="Open Buyer Desk →")
with col2:
    st.markdown("**Admin**")
    st.caption("Norm-document management and oversight.")
    st.page_link("pages/2_Admin_Desk.py", label="Open Admin Desk →")
    st.caption(":orange[Planned — v1.1]")
with col3:
    st.markdown("**Bidder**")
    st.caption("Self-service RFP upload and plain-language summary.")
    st.page_link("pages/3_Bidder_Desk.py", label="Open Bidder Desk →")
    st.caption(":orange[Planned — v1.1]")

st.divider()
if health_check():
    st.success(f"Backend API is reachable at {API_BASE}")
else:
    st.error(
        "Backend API is not reachable. Start it with:\n\n"
        "`uvicorn backend.api.main:app --reload --port 8000` (run from the repo root)"
    )
