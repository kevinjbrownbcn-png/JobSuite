"""JobPilot Mode B (Interview Assistant) — Streamlit page. Mirrors interview.html:
lists any match with a job description, lets the user start/resume/re-run a
persona-specific mock interview, and renders the turn-by-turn Q&A. Same jobsuite.db
as everywhere else — calls interview_api directly, no HTTP layer.
"""

import streamlit as st

import interview_api
import jobsuite_db
from jobsuite_config import load_config
from streamlit_common import apply_theme

st.set_page_config(page_title="Interview Assistant — JobSuite", page_icon="🎤", layout="wide")
apply_theme()

jobsuite_db.init_db()
config = load_config()

PERSONAS = {
    "recruiter": ("Recruiter / HR", "🧑‍💼"),
    "hiring_manager": ("Hiring Manager", "👔"),
    "department_manager": ("Department Manager", "📈"),
    "peer": ("Peer Interviewer", "🤝"),
}

st.title("🎤 Interview Assistant")
st.caption(
    "Practice with four stakeholder personas, scored turn by turn. Reuses JobPilot's "
    "ATS analysis when it exists; otherwise the job description (and tailored CV, if "
    "one was generated) is parsed on the spot."
)

if st.button("🔄 Refresh"):
    st.session_state.pop("interview_open", None)
    st.rerun()

conn = jobsuite_db.get_connection()
try:
    _, matches = interview_api.list_eligible_matches(conn)
finally:
    conn.close()

if not matches:
    st.info("No eligible applications yet. Once Hunter has a match with a job description, it'll show up here.")
else:
    for match in matches:
        with st.container(border=True):
            st.markdown(f"**{match['job_title']}** — {match['company']}")
            st.caption("JD + Tailored CV" if match.get("cv_doc_id") else "JD only")

            conn = jobsuite_db.get_connection()
            try:
                _, sessions = interview_api.list_sessions(conn, match["id"])
            finally:
                conn.close()
            # sessions come back ordered id DESC, so the first hit per persona is the latest.
            latest_by_persona = {}
            for s in sessions:
                latest_by_persona.setdefault(s["persona"], s)

            cols = st.columns(4)
            for col, (persona, (label, icon)) in zip(cols, PERSONAS.items()):
                with col:
                    if st.button(f"{icon} {label}", key=f"persona_{match['id']}_{persona}", use_container_width=True):
                        st.session_state["interview_open"] = (match["id"], persona)
                        st.rerun()
                    latest = latest_by_persona.get(persona)
                    if latest:
                        st.caption(f"{latest['overall_score']}%" if latest["status"] == "completed" else "in progress")

            open_key = st.session_state.get("interview_open")
            if open_key and open_key[0] == match["id"]:
                _, persona = open_key
                label, icon = PERSONAS[persona]
                st.divider()
                st.markdown(f"#### {icon} {label}")

                conn = jobsuite_db.get_connection()
                try:
                    latest = latest_by_persona.get(persona)
                    if latest:
                        status, session = interview_api.get_session(conn, latest["id"])
                    else:
                        status, session = interview_api.start_session(conn, match["id"], persona, config)
                finally:
                    conn.close()

                if status not in (200, 201):
                    st.error(session.get("error"))
                else:
                    if not session.get("resume_structured"):
                        st.caption(
                            "ⓘ No CV data available for this posting — questions are based on the job "
                            "description only."
                        )

                    for turn in session["turns"]:
                        with st.chat_message("assistant"):
                            st.write(turn["question"])
                        if turn.get("answer"):
                            with st.chat_message("user"):
                                st.write(turn["answer"])
                            if turn.get("answer_score") is not None:
                                st.caption(f"Score: {turn['answer_score']}%")
                                for f in turn.get("feedback") or []:
                                    st.caption(f"• {f}")
                                if turn.get("strengths"):
                                    st.success(", ".join(turn["strengths"]))
                                if turn.get("gaps"):
                                    st.warning(", ".join(turn["gaps"]))

                    if session["status"] == "completed":
                        st.metric("Session Score", f"{session.get('overall_score')}%")
                        if st.button("Start New Session", key=f"restart_{match['id']}_{persona}"):
                            conn = jobsuite_db.get_connection()
                            try:
                                interview_api.start_session(conn, match["id"], persona, config)
                            finally:
                                conn.close()
                            st.rerun()
                    else:
                        # Keying on turn count too so a resolved/follow-up turn always
                        # starts with an empty box instead of the previous answer.
                        answer_key = f"answer_{session['id']}_{len(session['turns'])}"
                        answer = st.text_area("Your answer", key=answer_key)
                        if st.button("Submit Answer", key=f"submit_{answer_key}") and answer.strip():
                            with st.spinner("Scoring your answer…"):
                                conn = jobsuite_db.get_connection()
                                try:
                                    interview_api.submit_turn(conn, session["id"], answer.strip(), config)
                                finally:
                                    conn.close()
                            st.rerun()
