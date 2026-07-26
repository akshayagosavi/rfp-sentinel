import streamlit as st

from shared.theme import inject_theme, render_letterhead

st.set_page_config(page_title="Bidder Desk — RFP Sentinel", page_icon="🛡️", layout="centered")
inject_theme()
render_letterhead("Procurement Compliance Desk", role="Bidder")

st.markdown("#### Bidder Dashboard — Not Yet Built")
st.info(
    "Planned for v1.1 per ROADMAP.md: bidder self-service upload (6–n bidders per RFP) "
    "and a plain-language RFP summary. This page is a placeholder so the navigation "
    "and shared styling are ready when the real screens are built."
)
