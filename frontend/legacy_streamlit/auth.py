"""v1: no login yet -- everyone is the buyer. Real credential login vs Postgres `users` arrives in v1.1."""
import streamlit as st


def ensure_role() -> str:
    st.session_state.setdefault("role", "buyer")
    return st.session_state["role"]
