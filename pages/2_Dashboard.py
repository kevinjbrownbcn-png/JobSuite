"""Dashboard — Streamlit page. Mirrors dashboard.html's two tabs (Dashboard Metrics,
Applications Viewer), reading/writing the same jobsuite.db via jobsuite_api directly.
"""

import re
from collections import Counter
from datetime import date

import pandas as pd
import streamlit as st

import jobsuite_api
import jobsuite_db
from jobsuite_config import load_config
from streamlit_common import apply_theme, categorize_role, load_json_config

st.set_page_config(page_title="Dashboard — JobSuite", page_icon="📊", layout="wide")
apply_theme()

jobsuite_db.init_db()
config = load_config()
ROLE_MAP = load_json_config("roles-config.json")

INTERVIEW_KEYWORDS = ["interview", "screen", "assessment", "technical", "panel", "l0", "l1", "l2"]
OFFER_KEYWORDS = ["offer", "hired", "accepted"]
STALE_DAYS_THRESHOLD = 14
# Statuses that don't count as "the company responded" for the Response Rate KPI —
# Sent/Received are pre-response states, Radio Silence is an explicit no-response.
NO_RESPONSE_STATUSES = ["Application Sent", "Application Received", "Radio Silence"]
# Rejection Rate KPI — the two explicit "this one's over, and not in your favor" statuses.
REJECTED_STATUSES = ["Application Declined", "Not moving forward after interview"]
# Active Pipeline KPI — everything NOT in this set still has some action pending.
# Offer Accepted is a terminal *good* outcome, same bucket as the terminal bad ones
# for "nothing left to track" purposes.
TERMINAL_STATUSES = ["Application Declined", "Not moving forward after interview", "Offer Accepted", "Radio Silence"]

st.title("📊 Pipeline Analytics")

conn = jobsuite_db.get_connection()
try:
    _, applications = jobsuite_api.list_applications(conn)
finally:
    conn.close()

tab_metrics, tab_viewer = st.tabs(["Dashboard Metrics", "Applications Viewer"])

# ------------------------------------------------------------------------------ Metrics

with tab_metrics:
    total = len(applications)
    status_counts = Counter()
    channel_counts = Counter()
    source_counts = Counter()
    category_counts = Counter()
    role_counts = Counter()
    interview_count = 0
    stale_count = 0
    response_days_sum = 0
    response_days_count = 0
    responded_count = 0
    offer_count = 0
    rejected_count = 0
    active_pipeline_count = 0
    apps_7d_count = 0
    apps_30d_count = 0

    for row in applications:
        status = (row.get("Status") or "Applied").strip()
        channel = (row.get("Applied Through") or "Direct/Other").strip()
        source = (row.get("Posting source") or "Direct/Other").strip()
        category = (row.get("Category") or "General").strip()
        job_title = row.get("Job Title") or ""

        status_counts[status] += 1
        channel_counts[channel] += 1
        source_counts[source] += 1
        category_counts[category] += 1
        role_counts[categorize_role(job_title, ROLE_MAP)] += 1

        if any(kw in status.lower() for kw in INTERVIEW_KEYWORDS):
            interview_count += 1

        response_time = row.get("Response Time") or ""
        if "Pending response" in response_time:
            m = re.search(r"\d+", response_time)
            if m and int(m.group()) > STALE_DAYS_THRESHOLD:
                stale_count += 1

        response_days = row.get("_response_days")
        if response_days is not None and status != "Radio Silence":
            response_days_sum += response_days
            response_days_count += 1

        if status not in NO_RESPONSE_STATUSES:
            responded_count += 1

        if any(kw in status.lower() for kw in OFFER_KEYWORDS):
            offer_count += 1
        if status in REJECTED_STATUSES:
            rejected_count += 1
        if status not in TERMINAL_STATUSES:
            active_pipeline_count += 1

        applied_date = jobsuite_api._parse_date(row.get("Date Applied"))
        if applied_date:
            age = (date.today() - applied_date).days
            if 0 <= age <= 7:
                apps_7d_count += 1
            if 0 <= age <= 30:
                apps_30d_count += 1

    top_category = max(category_counts, key=category_counts.get) if category_counts else "—"
    interview_rate = round((interview_count / total) * 100) if total else 0
    response_rate = round((responded_count / total) * 100) if total else 0
    offer_rate = round((offer_count / total) * 100) if total else 0
    rejection_rate = round((rejected_count / total) * 100) if total else 0
    avg_response = (
        jobsuite_api._format_duration_days(round(response_days_sum / response_days_count))
        if response_days_count else "—"
    )

    r1c1, r1c2, r1c3, r1c4 = st.columns(4)
    r1c1.metric("Total Applications", total)
    r1c2.metric("Active Interviews", interview_count)
    r1c3.metric("Interview Rate", f"{interview_rate}%")
    r1c4.metric("Response Rate", f"{response_rate}%")

    r2c1, r2c2, r2c3, r2c4 = st.columns(4)
    r2c1.metric("Offer Rate", f"{offer_rate}%")
    r2c2.metric("Rejection Rate", f"{rejection_rate}%")
    r2c3.metric("Active Pipeline", active_pipeline_count)
    r2c4.metric("Stale Trackings (>14d)", stale_count)

    r3c1, r3c2, r3c3, r3c4 = st.columns(4)
    r3c1.metric("Top Category", top_category)
    r3c2.metric("Avg Response Time", avg_response)
    r3c3.metric("Applications (Last 7 Days)", apps_7d_count)
    r3c4.metric("Applications (Last 30 Days)", apps_30d_count)

    st.divider()
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Application Funnel**")
        st.bar_chart(pd.DataFrame.from_dict(status_counts, orient="index", columns=["count"]))
    with c2:
        st.markdown("**Top Channels**")
        st.bar_chart(pd.DataFrame.from_dict(channel_counts, orient="index", columns=["count"]))
    with c3:
        st.markdown("**Role Types**")
        st.bar_chart(pd.DataFrame.from_dict(role_counts, orient="index", columns=["count"]))

    st.markdown("**Posting Sources**")
    source_df = pd.DataFrame(sorted(source_counts.items(), key=lambda x: -x[1]), columns=["Source", "Count"])
    st.dataframe(source_df, use_container_width=True, hide_index=True)

# ------------------------------------------------------------------------ Applications

with tab_viewer:
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        search = st.text_input("Text Search", placeholder="Company, title, notes...")
    with f2:
        category_filter = st.selectbox("Filter Category", ["ALL", *sorted({(r.get("Category") or "General") for r in applications})])
    with f3:
        status_filter = st.selectbox("Filter Status", ["ALL", *sorted({(r.get("Status") or "Applied") for r in applications})])
    with f4:
        source_filter = st.selectbox("Filter Source", ["ALL", *sorted({(r.get("Posting source") or "Direct/Other") for r in applications})])

    def matches_filters(row):
        if category_filter != "ALL" and (row.get("Category") or "General") != category_filter:
            return False
        if status_filter != "ALL" and (row.get("Status") or "Applied") != status_filter:
            return False
        if source_filter != "ALL" and (row.get("Posting source") or "Direct/Other") != source_filter:
            return False
        if search:
            haystack = " ".join([row.get("Job Title") or "", row.get("Company") or "", row.get("Notes") or ""]).lower()
            if search.lower() not in haystack:
                return False
        return True

    filtered = [r for r in applications if matches_filters(r)]
    st.caption(f"Showing {len(filtered)} record(s)")

    for row in filtered:
        rid = row["_id"]
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 1.5, 2, 3])
            with c1:
                title = row.get("Job Title") or ""
                url = row.get("Job URL") or ""
                if url.startswith("http"):
                    st.markdown(f"**[{title}]({url})** 🔗")
                else:
                    st.markdown(f"**{title}**")
                st.caption(row.get("Company") or "")
            with c2:
                st.caption(f"Applied: {row.get('Date Applied') or '—'}")
                st.caption(f"Reply: {row.get('First Response Date') or '—'}")
                st.caption(row.get("Response Time") or "")
            with c3:
                new_status = st.selectbox(
                    "Status", jobsuite_api.APPLICATION_STATUSES,
                    index=jobsuite_api.APPLICATION_STATUSES.index(row["Status"]) if row["Status"] in jobsuite_api.APPLICATION_STATUSES else 0,
                    key=f"status_{rid}", label_visibility="collapsed",
                )
                if new_status != row["Status"]:
                    conn = jobsuite_db.get_connection()
                    s, body = jobsuite_api.update_application(conn, rid, {"status": new_status}, config)
                    conn.close()
                    if s == 200:
                        if body.get("_archive_warning"):
                            st.warning(f"Status saved — archive webhook warning: {body['_archive_warning']}")
                        st.rerun()
                    else:
                        st.error(body.get("error"))
            with c4:
                new_notes = st.text_input(
                    "Notes", value=row.get("Notes") or "", key=f"notes_{rid}", label_visibility="collapsed",
                )
                if new_notes != (row.get("Notes") or ""):
                    conn = jobsuite_db.get_connection()
                    s, body = jobsuite_api.update_application(conn, rid, {"notes": new_notes}, config)
                    conn.close()
                    if s == 200:
                        st.rerun()
                    else:
                        st.error(body.get("error"))
