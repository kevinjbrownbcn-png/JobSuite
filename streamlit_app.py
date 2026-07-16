"""JobSuite — Streamlit home page. Equivalent of launcher.html: a landing page
pointing at the four functional pages (Hunter, Dashboard, JobPilot, Interview
Assistant), which live in pages/ and show up automatically in Streamlit's sidebar
navigation.

Run with:
    streamlit run streamlit_app.py

Shares the exact same jobsuite.db and config.json as the desktop app (launch_launcher.py)
as long as this file stays in the same folder as jobsuite_db.py / jobsuite_config.py —
data_dir() resolves to that folder in both cases.
"""

import streamlit as st

import jobsuite_db
from jobsuite_config import load_config
from streamlit_common import apply_theme

st.set_page_config(page_title="JobSuite — Control Center", page_icon="💼", layout="wide")
apply_theme()

jobsuite_db.init_db()
config = load_config()

st.title("💼 JobSuite — Control Center")
st.caption("Automated Job Search & Tracking — Streamlit edition")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.subheader("🔎 AI Job Hunter")
    st.write(
        "Run live web scrapes, analyze postings pasted by hand or by URL, batch-score a "
        "corporate careers hub, and manage staged matches through to the tracker."
    )
    st.page_link("pages/1_Hunter.py", label="Open Hunter", icon="🔎")

with col2:
    st.subheader("📊 Pipeline Analytics")
    st.write(
        "Review application metrics, manage statuses, filter and sort your full pipeline, "
        "and monitor response rates over time."
    )
    st.page_link("pages/2_Dashboard.py", label="Open Dashboard", icon="📊")

with col3:
    st.subheader("🧭 JobPilot")
    st.write(
        "Run a Claude-scored ATS fit analysis on each application's tailored CV against "
        "its job description."
    )
    st.page_link("pages/3_JobPilot.py", label="Open JobPilot", icon="🧭")

with col4:
    st.subheader("🎤 Interview Assistant")
    st.write(
        "Practice mock interviews with four stakeholder personas, each scoring "
        "your answers turn by turn."
    )
    st.page_link("pages/4_Interview.py", label="Open Interview Assistant", icon="🎤")

st.divider()

hunter_missing = [k for k in ("gemini_api_key", "gdrive_webhook", "docgen_webhook", "drive_cleanup_webhook") if not config.get(k)]
jobpilot_missing = [k for k in ("anthropic_api_key", "doc_fetch_webhook") if not config.get(k)]
if hunter_missing:
    st.warning(f"config.json is missing: {', '.join(hunter_missing)}. Some Hunter features won't work until these are set.")
if jobpilot_missing:
    st.warning(f"config.json is missing: {', '.join(jobpilot_missing)}. JobPilot's ATS Analyzer won't work until these are set.")
if not hunter_missing and not jobpilot_missing:
    st.success("config.json is fully configured.")

st.caption(f"Database: `{jobsuite_db.DB_PATH}`")
