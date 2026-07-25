"""
Single Streamlit app, role-routed via st.navigation() -- not 3 separate
apps. v1: only the buyer role has real pages; auth.py defaults everyone
to buyer until v1.1 adds real login.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

from auth import ensure_role

st.set_page_config(page_title="RFP Sentinel", layout="wide")

role = ensure_role()

PAGES_BY_ROLE = {
    "buyer": [
        st.Page("pages/buyer/1_rfp_setup.py", title="RFP Setup", icon="📄"),
        st.Page("pages/buyer/2_checkpoint_a.py", title="Checkpoint A", icon="✅"),
    ],
}

st.navigation(PAGES_BY_ROLE[role]).run()
