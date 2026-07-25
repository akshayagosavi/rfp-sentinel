"""Buyer page 2: poll processing status, review extracted criteria + compliance flags, approve to resume the graph."""
import requests
import streamlit as st

from api_client import approve_criteria, get_criteria, get_status

st.title("Checkpoint A: Human Review Required")

rfp_id = st.session_state.get("rfp_id") or st.text_input("RFP ID", value="")
if not rfp_id:
    st.info("Upload an RFP on the RFP Setup page first, or paste an RFP ID above.")
    st.stop()

try:
    status = get_status(rfp_id)["status"]
except requests.HTTPError:
    st.error(f"RFP ID `{rfp_id}` not found.")
    st.stop()

st.write(f"Status: **{status}**")

if status in ("extracting", "checking_compliance"):
    st.info("Still processing -- click refresh to check again.")
    if st.button("Refresh"):
        st.rerun()
    st.stop()

if status == "approved":
    st.success("Already approved. Checkpoint A complete for this RFP.")
    st.stop()

# status == "awaiting_checkpoint_a"
criteria = get_criteria(rfp_id)["criteria"]
st.write(f"{len(criteria)} criteria extracted.")

category_options = ["technical", "financial", "eligibility"]
edited_criteria = []
for c in criteria:
    with st.container(border=True):
        cols = st.columns([3, 1, 1])
        text = cols[0].text_area(
            "Criterion", value=c["text"], key=f"text_{c['id']}", label_visibility="collapsed"
        )
        mandatory = cols[1].checkbox("Mandatory", value=c["mandatory"], key=f"mand_{c['id']}")
        category = cols[2].selectbox(
            "Category", category_options, index=category_options.index(c["category"]),
            key=f"cat_{c['id']}",
        )
        if c.get("compliance_issue"):
            st.warning(f"Possible norm conflict: {c['compliance_issue']}")
            if c.get("compliance_citation"):
                st.caption(f"Citation: {c['compliance_citation']}")
        edited = dict(c)
        edited["text"] = text
        edited["mandatory"] = mandatory
        edited["category"] = category
        edited_criteria.append(edited)

if st.button("Approve & Continue"):
    approve_criteria(rfp_id, edited_criteria)
    st.success("Approved. Checkpoint A complete.")
