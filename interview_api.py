"""JobPilot Mode B (Interview Assistant) — CRUD over `interview_sessions`/`interview_turns`.

Same transport-agnostic shape as jobpilot_api.py: functions take an open `conn`
and return a (status_code, json_serializable_body) tuple. Routing lives in
jobsuite_api.py's dispatch() (an `interview-sessions` resource branch), not here.
"""

import json
from datetime import datetime, timezone

import jobsuite_claude

PERSONAS = {"recruiter", "hiring_manager", "department_manager", "peer"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_error(message, status=400):
    return status, {"error": message}


def _row_to_dict(row):
    return {k: row[k] for k in row.keys()}


def _session_row_to_json(row):
    d = _row_to_dict(row)
    for field in ("resume_structured", "job_structured"):
        d[field] = json.loads(d[field]) if d.get(field) else None
    d["rubric"] = json.loads(d["rubric"]) if d.get("rubric") else []
    return d


def _turn_row_to_json(row):
    d = _row_to_dict(row)
    d["criterion_scores"] = json.loads(d["criterion_scores"]) if d.get("criterion_scores") else None
    for field in ("feedback", "strengths", "gaps"):
        d[field] = json.loads(d[field]) if d.get(field) else []
    return d


def list_eligible_matches(conn):
    """Any match with a job description is practiceable — broader than JobPilot
    Mode A's eligibility, since older postings that predate a tailored CV/ATS run
    should still be usable for interview practice (see _resolve_context)."""
    rows = conn.execute(
        "SELECT * FROM matches WHERE job_description IS NOT NULL AND job_description != '' "
        "ORDER BY id DESC"
    ).fetchall()
    return 200, [_row_to_dict(r) for r in rows]


def _resolve_context(conn, match, config):
    """3-tier fallback, cheapest first:
    1. Reuse the latest prep_session's structured data if one exists (JobPilot
       Mode A already ran) — zero extra Claude calls.
    2. No prep_session: parse the job description on demand (always local, no
       fetch needed), and the tailored CV too if the match has one.
    3. No tailored CV either: proceed with resume_structured = None — the
       interview runs JD/role-focused only.
    Returns (resume_structured, job_structured)."""
    prep_row = conn.execute(
        "SELECT resume_structured, job_structured FROM prep_sessions "
        "WHERE match_id = ? ORDER BY id DESC LIMIT 1",
        (match["id"],),
    ).fetchone()
    if prep_row and prep_row["job_structured"]:
        resume_structured = json.loads(prep_row["resume_structured"]) if prep_row["resume_structured"] else None
        job_structured = json.loads(prep_row["job_structured"])
        return resume_structured, job_structured

    api_key = config.get("anthropic_api_key")
    job_structured = jobsuite_claude.parse_job_description(match["job_description"], api_key)

    resume_structured = None
    if match["cv_doc_id"]:
        resume_text = jobsuite_claude.fetch_doc_text(config.get("doc_fetch_webhook"), match["cv_doc_id"])
        resume_structured = jobsuite_claude.parse_resume(resume_text, api_key)

    return resume_structured, job_structured


def start_session(conn, match_id, persona, config):
    if persona not in PERSONAS:
        return _json_error(f"Unknown persona: {persona}", 400)

    match = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if not match:
        return _json_error("Match not found.", 404)
    if not match["job_description"]:
        return _json_error("This match has no job description to interview against.", 409)

    try:
        resume_structured, job_structured = _resolve_context(conn, match, config)
        starter = jobsuite_claude.start_interview(
            persona, resume_structured, job_structured, config.get("anthropic_api_key")
        )
    except Exception as e:
        return _json_error(str(e), 502)

    now = _now()
    cur = conn.execute(
        """INSERT INTO interview_sessions
           (match_id, persona, status, resume_structured, job_structured, goal, tone,
            rubric, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            match_id, persona, "in_progress",
            json.dumps(resume_structured) if resume_structured else None,
            json.dumps(job_structured), starter.get("goal"), starter.get("tone"),
            json.dumps(starter.get("rubric") or []), now, now,
        ),
    )
    session_id = cur.lastrowid
    conn.execute(
        "INSERT INTO interview_turns (session_id, turn_index, question, created_at) VALUES (?,?,?,?)",
        (session_id, 0, starter.get("firstQuestion"), now),
    )
    conn.commit()
    return get_session(conn, session_id)


def submit_turn(conn, session_id, answer, config):
    session = conn.execute("SELECT * FROM interview_sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        return _json_error("Interview session not found.", 404)
    if session["status"] == "completed":
        return _json_error("This interview session is already completed.", 409)

    turns = conn.execute(
        "SELECT * FROM interview_turns WHERE session_id = ? ORDER BY turn_index", (session_id,)
    ).fetchall()
    current_turn = turns[-1]
    if current_turn["answer"] is not None:
        return _json_error("The current question already has an answer recorded.", 409)

    resume_structured = json.loads(session["resume_structured"]) if session["resume_structured"] else None
    job_structured = json.loads(session["job_structured"])
    history = [{"question": t["question"], "answer": t["answer"]} for t in turns]

    try:
        result = jobsuite_claude.interview_turn(
            session["persona"], resume_structured, job_structured, history, answer,
            config.get("anthropic_api_key"),
        )
    except Exception as e:
        return _json_error(str(e), 502)

    now = _now()
    conn.execute(
        """UPDATE interview_turns SET answer = ?, answer_score = ?, criterion_scores = ?,
           feedback = ?, strengths = ?, gaps = ? WHERE id = ?""",
        (
            answer, result.get("answerScore"), json.dumps(result.get("criterionScores") or {}),
            json.dumps(result.get("feedback") or []), json.dumps(result.get("strengths") or []),
            json.dumps(result.get("gaps") or []), current_turn["id"],
        ),
    )

    next_action = result.get("nextAction")
    if next_action == "follow_up" and result.get("followUpQuestion"):
        conn.execute(
            "INSERT INTO interview_turns (session_id, turn_index, question, created_at) VALUES (?,?,?,?)",
            (session_id, current_turn["turn_index"] + 1, result["followUpQuestion"], now),
        )
        conn.execute("UPDATE interview_sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    else:
        # "next_persona" is treated the same as "end_session" here — personas run
        # individually, not as a forced sequence, so there's no next persona to hand off to.
        scored = conn.execute(
            "SELECT answer_score FROM interview_turns WHERE session_id = ? AND answer_score IS NOT NULL",
            (session_id,),
        ).fetchall()
        overall = round(sum(r["answer_score"] for r in scored) / len(scored)) if scored else None
        conn.execute(
            "UPDATE interview_sessions SET status = 'completed', overall_score = ?, updated_at = ? WHERE id = ?",
            (overall, now, session_id),
        )

    conn.commit()
    return get_session(conn, session_id)


def list_sessions(conn, match_id):
    rows = conn.execute(
        "SELECT * FROM interview_sessions WHERE match_id = ? ORDER BY id DESC", (match_id,)
    ).fetchall()
    return 200, [_session_row_to_json(r) for r in rows]


def get_session(conn, session_id):
    row = conn.execute("SELECT * FROM interview_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        return _json_error("Interview session not found.", 404)
    session = _session_row_to_json(row)
    turns = conn.execute(
        "SELECT * FROM interview_turns WHERE session_id = ? ORDER BY turn_index", (session_id,)
    ).fetchall()
    session["turns"] = [_turn_row_to_json(t) for t in turns]
    return 200, session
