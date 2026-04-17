"""AML Rule Tester — Streamlit entry point.

Run with:
    streamlit run app.py
"""
import os
import sys

# Ensure the project root is on the path so all imports resolve correctly
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

from ui.pages import scenario_input
from ui.state import init_state, reset_state

st.set_page_config(
    page_title="AML Scenario Builder",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

init_state()

with st.sidebar:
    st.markdown("## AML Scenario Builder")
    if st.button("+ New Scenario", use_container_width=True):
        reset_state()
        st.session_state.step = "scenario_input"
        st.rerun()

    # ── Settings ──────────────────────────────────────────────────────────────
    # st.markdown("---")
    # st.markdown("**Settings**")
    # api_key_input = st.text_input(
    #     "Anthropic API Key",
    #     value=st.session_state.get("api_key", ""),
    #     type="password",
    #     placeholder="sk-ant-...",
    #     help="Paste your Anthropic API key here. Overrides the ANTHROPIC_API_KEY env variable.",
    # )
    # if api_key_input != st.session_state.get("api_key", ""):
    #     st.session_state.api_key = api_key_input
    #     st.rerun()
    #
    # if st.session_state.get("api_key"):
    #     st.caption("✓ API key set")
    # elif os.environ.get("ANTHROPIC_API_KEY"):
    #     st.caption("✓ Using env variable")
    # else:
    #     st.caption("⚠ No API key configured")

    if st.session_state.status_log:
        st.markdown("---")
        st.markdown("**Generation Log**")
        for msg in st.session_state.status_log[-10:]:
            st.caption(msg)

# ── Page routing ──────────────────────────────────────────────────────────────
scenario_input.render()
