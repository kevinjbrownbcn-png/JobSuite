"""JobPilot Mode A (ATS Analyzer) — Streamlit page. Mirrors jobpilot.html: lists
matches with a tailored CV ready (Processed status + cv_doc_id), lets the user run a
Claude-scored ATS fit analysis, and shows the result. Same jobsuite.db as everywhere
else — calls jobpilot_api directly, no HTTP layer.
"""

import streamlit as st

import jobpilot_api
import jobsuite_db
from jobsuite_config import load_config
from streamlit_common import apply_theme

st.set_page_config(page_title="JobPilot — JobSuite", page_icon="🧭", layout="wide")
apply_theme()

jobsuite_db.init_db()
config = load_config()

st.title("🧭 JobPilot")
st.caption("ATS Analyzer — Claude-scored CV/JD fit, using the tailored CV generated for each application.")

if st.button("🔄 Refresh"):
    st.rerun()

conn = jobsuite_db.get_connection()
try:
    _, matches = jobpilot_api.list_eligible_matches(conn)
finally:
    conn.close()

if not matches:
    st.info(
        "No eligible applications yet. Once a Staged Match has a tailored CV generated "
        "(status \"Processed\"), it'll show up here."
    )
else:
    for match in matches:
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                st.markdown(f"**{match['job_title']}** — {match['company']}")
                if match.get("cv_doc_url"):
                    st.markdown(f"[Tailored CV ↗]({match['cv_doc_url']})")

            conn = jobsuite_db.get_connection()
            try:
                _, sessions = jobpilot_api.list_prep_sessions(conn, match["id"])
            finally:
                conn.close()

            with c2:
                if sessions:
                    st.metric("Latest Score", f"{sessions[0]['overall_score']}%")
                else:
                    st.caption("No analysis yet")

            with c3:
                if st.button("Run ATS Analysis", key=f"run_{match['id']}"):
                    with st.spinner("Fetching the tailored CV and scoring it against the job description…"):
                        conn = jobsuite_db.get_connection()
                        try:
                            status, body = jobpilot_api.create_prep_session(conn, match["id"], config)
                        finally:
                            conn.close()
                    if status == 201:
                        st.session_state[f"jobpilot_result_{match['id']}"] = body
                        st.rerun()
                    else:
                        st.error(body.get("error"))

            result = sessions[0] if sessions else None
            latest_key = f"jobpilot_result_{match['id']}"
            if latest_key in st.session_state:
                result = st.session_state[latest_key]

            if result:
                with st.expander("View ATS Analysis", expanded=(latest_key in st.session_state)):
                    st.metric("Overall Fit", f"{result.get('overall_score')}%")

                    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
                    sc1.metric("Skills", result.get("skills_match"))
                    sc2.metric("Seniority", result.get("seniority_match"))
                    sc3.metric("Domain", result.get("domain_match"))
                    sc4.metric("Experience", result.get("experience_match"))
                    sc5.metric("Format Risk", result.get("format_risk"))

                    with st.expander("ⓘ What do these scores mean?"):
                        st.markdown(
                            "- **Skills Match** — how many of the job's explicitly-named tools/skills show up "
                            "in the CV. Higher is better.\n"
                            "- **Seniority Match** — whether the CV's title/scope/years line up with the "
                            "seniority the role expects. Higher is better.\n"
                            "- **Domain Match** — how closely the candidate's industry/domain background "
                            "aligns with this role's field. Higher is better.\n"
                            "- **Experience Match** — how well the depth and relevance of past roles fits "
                            "what's being asked. Higher is better.\n"
                            "- **Format Risk** — the odd one out: *higher means worse*. Flags things like "
                            "missing contact info or a structure that could trip up ATS parsing or a human "
                            "skim-read.\n"
                            "- **Overall Fit** — a fixed weighted formula, not a separate judgment call: "
                            "30% Skills + 20% Seniority + 20% Domain + 15% Experience + 15% (100 − Format Risk). "
                            "Same weighting every time, so scores are comparable across applications."
                        )

                    st.write(result.get("summary") or "")

                    sk1, sk2 = st.columns(2)
                    with sk1:
                        st.markdown("**Matched Skills**")
                        st.write(", ".join(result.get("matched_skills") or []) or "None")
                    with sk2:
                        st.markdown("**Missing Skills**")
                        st.write(", ".join(result.get("missing_skills") or []) or "None")

                    st.markdown("**Missing Evidence**")
                    for item in result.get("missing_evidence") or []:
                        st.write(f"- {item}")

                    st.markdown("**Risks**")
                    for item in result.get("risks") or []:
                        st.write(f"- {item}")

                    st.markdown("**Recommendations**")
                    for item in result.get("recommendations") or []:
                        st.write(f"- {item}")
