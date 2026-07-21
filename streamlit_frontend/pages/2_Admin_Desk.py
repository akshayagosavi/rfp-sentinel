import streamlit as st

from shared.theme import inject_theme, render_letterhead

st.set_page_config(page_title="Admin Desk — RFP Sentinel", page_icon="🛡️", layout="centered")
inject_theme()
render_letterhead("Procurement Compliance Desk", role="Admin")

st.markdown("#### Admin Dashboard — Not Yet Built")
st.info(
    "Planned for v1.1 per ROADMAP.md: role-based auth (Buyer / Admin / Bidder), "
    "norm-document management, and user/RFP oversight. This page is a placeholder "
    "so the navigation and shared styling are ready when the real screens are built."
)
