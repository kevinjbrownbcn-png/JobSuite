"""JobSuite — Streamlit home page. Equivalent of launcher.html: a landing page
pointing at the two functional pages (Hunter, Dashboard), which live in pages/ and
show up automatically in Streamlit's sidebar navigation.

Run with:
    streamlit run streamlit_app.py

Shares the exact same jobsuite.db and config.json as the desktop app (launch_launcher.py)
as long as this file stays in the same folder as jobsuite_db.py / jobsuite_config.py —
exe_dir() resolves to that folder in both cases.
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

col1, col2 = st.columns(2)
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

st.divider()

missing = [k for k in ("gemini_api_key", "gdrive_webhook", "docgen_webhook", "drive_cleanup_webhook") if not config.get(k)]
if missing:
    st.warning(f"config.json is missing: {', '.join(missing)}. Some Hunter features won't work until these are set.")
else:
    st.success("config.json is fully configured.")

st.caption(f"Database: `{jobsuite_db.DB_PATH}`")
