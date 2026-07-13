"""Small shared helpers for the Streamlit pages — kept separate from jobsuite_api.py
since these are UI-layer concerns (JSON config loading, role categorization for the
Dashboard charts, theming), not part of the transport-agnostic API/DB layer.
"""

import json
import os

import streamlit as st

from jobsuite_config import data_dir


def load_json_config(filename: str) -> dict:
    path = os.path.join(data_dir(), filename)
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def categorize_role(job_title: str, role_map: dict) -> str:
    """Mirrors dashboard-viewer.js's ROLE_MAPPING_DICTIONARY keyword matching."""
    title_lower = (job_title or "").lower()
    for role_type, keywords in role_map.items():
        if any(kw.lower() in title_lower for kw in keywords):
            return role_type
    return "Uncategorized / Other"


# .streamlit/config.toml sets the *default* (dark) base theme — Streamlit's own theme
# engine has no runtime toggle, so light mode is achieved by injecting CSS overrides
# targeting Streamlit's stable data-testid hooks, gated on a session_state flag that
# persists across pages (shared automatically within one multipage session).
_LIGHT_THEME_CSS = """
<style>
[data-testid="stAppViewContainer"], [data-testid="stMain"], .stApp {
    background-color: #f8fafc !important;
    color: #0f172a !important;
}
[data-testid="stHeader"] { background-color: #e2e8f0 !important; }
[data-testid="stSidebar"] { background-color: #e2e8f0 !important; }
[data-testid="stSidebar"] * { color: #0f172a !important; }
h1, h2, h3, h4, h5, h6, p, span, label, li,
.stMarkdown, [data-testid="stMarkdownContainer"] { color: #0f172a !important; }
[data-testid="stCaptionContainer"], .stCaption, small { color: #475569 !important; }
[data-testid="stMetric"] {
    background-color: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 8px;
    padding: 8px;
}
[data-testid="stMetricLabel"] { color: #475569 !important; }
[data-testid="stMetricValue"] { color: #0f172a !important; }
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stExpander"] {
    background-color: #ffffff !important;
    border-color: #cbd5e1 !important;
}
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
    background-color: #ffffff !important;
    color: #0f172a !important;
    border-color: #cbd5e1 !important;
}
[data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button {
    background-color: #ffffff !important;
    color: #0f172a !important;
    border: 1px solid #cbd5e1 !important;
}
[data-testid="stButton"] button:hover { border-color: #0d9488 !important; color: #0d9488 !important; }
[data-testid="stDataFrame"], [data-testid="stTable"] { background-color: #ffffff !important; }
a { color: #0d9488 !important; }
</style>
"""


def apply_theme() -> None:
    """Renders the dark/light toggle in the sidebar and injects light-theme CSS
    overrides when active. Defaults to dark (matching .streamlit/config.toml's base
    theme); the choice lives in session_state, which Streamlit shares across pages
    within one multipage session, so it doesn't need to be set on every page."""
    if "theme" not in st.session_state:
        st.session_state.theme = "dark"

    with st.sidebar:
        is_light = st.toggle(
            "☀️ Light theme", value=st.session_state.theme == "light", key="theme_toggle",
        )
        st.session_state.theme = "light" if is_light else "dark"

    if st.session_state.theme == "light":
        st.markdown(_LIGHT_THEME_CSS, unsafe_allow_html=True)
