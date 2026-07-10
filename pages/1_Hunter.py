"""Hunter — Streamlit page. Mirrors hunter.html's three tabs (Web Job Scanner, Manual
Audit, Staged Matches), calling jobsuite_gemini/jobsuite_api directly — no HTTP layer,
same jobsuite.db the desktop app uses.
"""

import streamlit as st

import jobsuite_api
import jobsuite_db
import jobsuite_gemini as gemini
from jobsuite_config import load_config
from streamlit_common import load_json_config

st.set_page_config(page_title="Hunter — JobSuite", page_icon="🔎", layout="wide")

jobsuite_db.init_db()
config = load_config()
profiles = load_json_config("hunter-profiles.json")
POSTING_SOURCES = profiles.get("postingSources", [])
PROFILE_VALUES = [p["value"] for p in profiles.get("profiles", [])]

st.title("🔎 AI Job Hunter")

if "pending_jobs" not in st.session_state:
    st.session_state.pending_jobs = []


def posting_source_input(key_prefix):
    options = ["— Select —", *POSTING_SOURCES, "Other..."]
    choice = st.selectbox("Posting Source", options, key=f"{key_prefix}_posting_source")
    if choice == "Other...":
        return st.text_input("Custom posting source", key=f"{key_prefix}_posting_source_other")
    if choice == "— Select —":
        return ""
    return choice


def persist_posting_source(value):
    """Appends a custom "Other" entry to hunter-profiles.json (shared with the desktop
    app's /api/posting-sources) so it shows up in the dropdown next time — no code change
    needed. Cheap no-op if the value is already known."""
    if value and value not in POSTING_SOURCES:
        jobsuite_api.add_posting_source({"source": value})


tab_scan, tab_manual, tab_staged = st.tabs(["🔎 Web Job Scanner", "🎯 Manual Audit", "🗂️ Staged Matches"])

# --------------------------------------------------------------------- Web Job Scanner

with tab_scan:
    st.subheader("Configure Automated Market Scan")

    role_options = [r["value"] for r in profiles.get("roles", [])]
    default_roles = [r["value"] for r in profiles.get("roles", []) if r.get("defaultChecked")]
    selected_roles = st.multiselect("Target Roles", role_options, default=default_roles)
    custom_role = st.text_input("Add a custom role title (optional)")
    if custom_role.strip():
        selected_roles = [*selected_roles, custom_role.strip()]

    c1, c2, c3 = st.columns(3)
    with c1:
        location = st.text_input("Location Criteria", value=profiles.get("defaultLocation", ""))
    with c2:
        time_window = st.selectbox("Search Window", ["the last 24 hours", "the last 3 days", "the last 7 days"], index=2)
    with c3:
        focus = st.text_input("Niche Keywords", value=profiles.get("defaultFocus", ""))

    if st.button("🚀 Scan Live Web for Roles", type="primary"):
        if not selected_roles:
            st.error("Select at least one role.")
        else:
            with st.spinner("Harvesting open web postings, ranking matches, checking skill gaps…"):
                try:
                    jobs = gemini.scan_web_for_jobs(
                        selected_roles, location, time_window, focus,
                        config.get("gemini_api_key"), config.get("gdrive_webhook"),
                    )
                    # Dedup against matches already staged in the DB — a more durable
                    # equivalent of the desktop's 7-day localStorage registry, since
                    # Streamlit has direct DB access anyway.
                    conn = jobsuite_db.get_connection()
                    existing = {
                        (r["job_title"].lower().strip(), r["company"].lower().strip())
                        for r in conn.execute("SELECT job_title, company FROM matches").fetchall()
                    }
                    conn.close()
                    fresh = [
                        j for j in jobs
                        if (j.get("job_title", "").lower().strip(), j.get("company", "").lower().strip()) not in existing
                    ]
                    st.session_state.pending_jobs.extend(fresh)
                    st.success(f"Found {len(jobs)} role(s) — {len(fresh)} new after filtering already-staged matches.")
                except Exception as e:
                    st.error(f"Scan failed: {e}")

# ------------------------------------------------------------------------- Manual Audit

with tab_manual:
    st.subheader("Manual Audit")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**📋 Analyze Verbatim Description**")
        with st.form("verbatim_form"):
            v_title = st.text_input("Position Title (optional)")
            v_company = st.text_input("Company / Studio (optional)")
            v_url = st.text_input("Job Posting URL (optional)")
            v_applied_through = st.text_input("Applied Through", key="v_applied_through")
            v_posting_source = posting_source_input("v")
            v_profile = st.selectbox("Alignment Context", PROFILE_VALUES, key="v_profile")
            v_description = st.text_area("Job Description Text", height=150)
            v_submit = st.form_submit_button("⚡ Run Skillset Audit")
        if v_submit:
            if not v_description.strip():
                st.error("Paste a job description first.")
            else:
                with st.spinner("Auditing raw text description…"):
                    try:
                        job = gemini.analyze_manual_text(
                            v_description, v_profile, v_title, v_company,
                            config.get("gemini_api_key"), config.get("gdrive_webhook"),
                        )
                        if v_title.strip():
                            job["job_title"] = v_title.strip()
                        if v_company.strip():
                            job["company"] = v_company.strip()
                        if v_url.strip():
                            job["link"] = v_url.strip()
                        job["description"] = v_description
                        job["applied_through"] = v_applied_through or None
                        job["posting_source"] = v_posting_source or None
                        persist_posting_source(v_posting_source)
                        st.session_state.pending_jobs.append(job)
                        st.success("Analysis complete — see Discovered Jobs below.")
                    except Exception as e:
                        st.error(f"Analysis failed: {e}")

    with col2:
        st.markdown("**🔗 Analyze Direct URL**")
        with st.form("url_form"):
            u_profile = st.selectbox("Alignment Context", PROFILE_VALUES, key="u_profile")
            u_url = st.text_input("Job Posting Link")
            u_applied_through = st.text_input("Applied Through", key="u_applied_through")
            u_posting_source = posting_source_input("u")
            u_submit = st.form_submit_button("📥 Analyze URL Posting")
        if u_submit:
            if not u_url.strip():
                st.error("Paste a job posting URL first.")
            else:
                with st.spinner("Reading target webpage…"):
                    try:
                        job = gemini.analyze_manual_url(
                            u_url.strip(), u_profile, config.get("gemini_api_key"), config.get("gdrive_webhook"),
                        )
                        job["applied_through"] = u_applied_through or None
                        job["posting_source"] = u_posting_source or None
                        persist_posting_source(u_posting_source)
                        st.session_state.pending_jobs.append(job)
                        st.success("Analysis complete — see Discovered Jobs below.")
                    except Exception as e:
                        st.error(f"Analysis failed: {e}")

    with col3:
        st.markdown("**🏢 Scan Corporate Careers Hub**")
        with st.form("hub_form"):
            h_profile = st.selectbox("Alignment Context", PROFILE_VALUES, key="h_profile")
            h_url = st.text_input("Careers Portal Main Index URL")
            h_applied_through = st.text_input("Applied Through", key="h_applied_through")
            h_posting_source = posting_source_input("h")
            h_submit = st.form_submit_button("🔮 Batch Process Hub")
        if h_submit:
            if not h_url.strip():
                st.error("Paste a careers portal URL first.")
            else:
                with st.spinner("Crawling careers hub, scoring each posting…"):
                    try:
                        jobs = gemini.analyze_careers_hub(h_url.strip(), h_profile, config.get("gemini_api_key"))
                        for j in jobs:
                            j["applied_through"] = h_applied_through or None
                            j["posting_source"] = h_posting_source or None
                        persist_posting_source(h_posting_source)
                        st.session_state.pending_jobs.extend(jobs)
                        st.success(f"Found and analyzed {len(jobs)} role(s) — see Discovered Jobs below.")
                    except Exception as e:
                        st.error(f"Hub scan failed: {e}")

# ---------------------------------------------------------------------- Staged Matches

with tab_staged:
    st.subheader("Staged Matches")
    if st.button("🔄 Refresh", key="refresh_staged"):
        st.rerun()

    conn = jobsuite_db.get_connection()
    try:
        _, matches = jobsuite_api.list_matches(conn, {})
    finally:
        conn.close()

    STATUS_LABELS = {
        "Draft": "Draft", "New": "Queued for Prep", "Processed": "Docs Ready",
        "Applied": "Applied", "Migrated to Tracker": "✓ In Tracker",
        "Discarded": "Discarding…", "Purged": "Discarded", "N/A": "N/A",
    }

    if not matches:
        st.info("No staged matches yet — export a role above to see it here.")
    else:
        for match in matches:
            mid, status = match["id"], match["status"]
            with st.container(border=True):
                c1, c2 = st.columns([3, 2])
                with c1:
                    st.markdown(f"**{match['job_title']}** — {match['company']}")
                    st.caption(f"{match.get('match_score', '—')}% match · {STATUS_LABELS.get(status, status)}")
                    if (match.get("job_url") or "").startswith("http"):
                        st.markdown(f"[View ↗]({match['job_url']})")

                with c2:
                    if status in ("Draft", "New"):
                        label = "Retry: Send to Prep" if status == "New" else "Send to Prep"
                        if st.button(label, key=f"prep_{mid}"):
                            with st.spinner("Requesting CV/cover letter generation…"):
                                conn = jobsuite_db.get_connection()
                                s, body = jobsuite_api.update_match(conn, mid, {"status": "New"}, config)
                                conn.close()
                            if s == 200:
                                st.success(f"Moved to {body['status']}.")
                                st.rerun()
                            else:
                                st.error(body.get("error"))
                    elif status == "Processed":
                        if st.button("Mark as Applied", key=f"apply_{mid}"):
                            with st.spinner("Recording application…"):
                                conn = jobsuite_db.get_connection()
                                s, body = jobsuite_api.update_match(conn, mid, {"status": "Applied"}, config)
                                conn.close()
                            if s == 200:
                                st.success(f"Moved to {body['status']}.")
                                st.rerun()
                            else:
                                st.error(body.get("error"))

                    if status not in ("Migrated to Tracker", "Purged"):
                        label = "Retry Cleanup" if status == "Discarded" else "Discard"
                        if st.button(label, key=f"discard_{mid}"):
                            conn = jobsuite_db.get_connection()
                            s, body = jobsuite_api.update_match(conn, mid, {"status": "Discarded"}, config)
                            conn.close()
                            if s == 200:
                                if body.get("_discard_warning"):
                                    st.warning(f"Marked Discarded — cleanup pending: {body['_discard_warning']}")
                                else:
                                    st.success(f"Now {body['status']}.")
                                st.rerun()
                            else:
                                st.error(body.get("error"))

                with st.expander("Job Description"):
                    new_desc = st.text_area(
                        "Description", value=match.get("job_description") or "",
                        key=f"desc_{mid}", height=150, label_visibility="collapsed",
                    )
                    if st.button("Save Description", key=f"save_desc_{mid}"):
                        conn = jobsuite_db.get_connection()
                        s, body = jobsuite_api.update_match(conn, mid, {"job_description": new_desc}, config)
                        conn.close()
                        if s == 200:
                            st.success("Saved.")
                            st.rerun()
                        else:
                            st.error(body.get("error"))

# ------------------------------------------------------------- Discovered Jobs (shared)
# Lives outside the tabs so it's visible regardless of which discovery method was used —
# mirrors the desktop's single shared job-card list feeding one export action.

st.divider()
st.subheader(f"Discovered Jobs ({len(st.session_state.pending_jobs)})")

if not st.session_state.pending_jobs:
    st.info("No pending results yet. Run a scan or manual audit above.")
else:
    to_export = []
    for i, job in enumerate(st.session_state.pending_jobs):
        with st.container(border=True):
            c1, c2, c3 = st.columns([5, 1, 1])
            with c1:
                score = job.get("match_score", 0)
                st.markdown(
                    f"**{job.get('job_title', 'Untitled')}** — {job.get('company', 'Unknown')}  \n"
                    f"`{score}% match` · {job.get('location', '')}"
                )
                if job.get("summary"):
                    st.caption(job["summary"])
                gaps = job.get("skills_gaps") or []
                if gaps:
                    st.write(" ".join(f"`{g}`" for g in gaps))
                if (job.get("link") or "").startswith("http"):
                    st.markdown(f"[Open Original Posting ↗]({job['link']})")
            with c2:
                if st.checkbox("Export", key=f"select_{i}", value=True):
                    to_export.append(job)
            with c3:
                # Store on the tracker for reference without acting on it — e.g. a
                # dead/expired listing (410/404) — mirrors the desktop's per-card
                # Discard button, reusing create_matches' same _discard flag.
                if st.button("Discard", key=f"discard_{i}"):
                    conn = jobsuite_db.get_connection()
                    try:
                        status, body = jobsuite_api.create_matches(conn, {"jobs": [{**job, "_discard": True}]}, config)
                    finally:
                        conn.close()
                    if status == 201:
                        label = f'"{job.get("job_title", "Untitled")}" at {job.get("company", "Unknown")}'
                        msg = f"{label} discarded — kept on the tracker for reference, no action needed."
                        if body.get("_discard_warnings"):
                            msg += f" (Drive cleanup skipped: {body['_discard_warnings'][0]['warning']})"
                        st.info(msg)
                        st.session_state.pending_jobs = [j for j in st.session_state.pending_jobs if j is not job]
                        st.rerun()
                    else:
                        st.error(body.get("error", "Discard failed."))

    b1, b2 = st.columns(2)
    with b1:
        if st.button(f"📦 Export {len(to_export)} Selected to Staged Matches", type="primary", disabled=not to_export):
            conn = jobsuite_db.get_connection()
            try:
                status, body = jobsuite_api.create_matches(conn, {"jobs": to_export}, config)
            finally:
                conn.close()
            if status == 201:
                msg = f"Exported {body['count']} job(s) to Staged Matches."
                if body.get("_auto_docgen_sent"):
                    msg += f" {len(body['_auto_docgen_sent'])} sent straight to Doc Creation (90%+ match)."
                if body.get("_auto_docgen_failed"):
                    msg += f" {len(body['_auto_docgen_failed'])} high-match job(s) stayed at Draft — doc generation failed, retry from Staged Matches."
                st.success(msg)
                st.session_state.pending_jobs = [j for j in st.session_state.pending_jobs if j not in to_export]
                st.rerun()
            else:
                st.error(body.get("error", "Export failed."))
    with b2:
        if st.button("Clear all pending results"):
            st.session_state.pending_jobs = []
            st.rerun()
