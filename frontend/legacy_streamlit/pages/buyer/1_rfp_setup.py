"""Buyer page 1: upload an RFP PDF, kick off extraction + compliance checking."""
import streamlit as st

from api_client import upload_rfp

st.title("RFP Setup")
st.caption(
    "Upload the RFP/tender PDF. Category is fixed to Electronics and evaluation "
    "method defaults to L1 for v1. Extraction and compliance checking run in "
    "the background -- this can take a while on CPU-only hardware."
)

uploaded = st.file_uploader("RFP PDF", type="pdf")

with st.expander("Advanced (testing only)"):
    limit = st.number_input(
        "Limit number of criteria processed (0 = no limit, full real run)",
        min_value=0, value=0, step=1,
    )

if st.button("Upload & Start Evaluation", disabled=uploaded is None):
    with st.spinner("Uploading..."):
        result = upload_rfp(
            uploaded.getvalue(), uploaded.name, max_criteria=limit or None
        )
    st.session_state["rfp_id"] = result["rfp_id"]
    st.success(f"Uploaded. RFP ID: {result['rfp_id']}")
    st.info("Open **Checkpoint A** from the sidebar to track progress and review extracted criteria.")

if st.session_state.get("rfp_id"):
    st.divider()
    st.write(f"Current RFP ID in progress: `{st.session_state['rfp_id']}`")
