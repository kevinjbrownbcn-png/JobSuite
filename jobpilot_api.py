"""JobPilot Mode A (ATS Analyzer) — CRUD over `prep_sessions`.

Kept transport-agnostic like jobsuite_api.py: functions take an open `conn` and
return a (status_code, json_serializable_body) tuple. Routing lives in
jobsuite_api.py's dispatch() (a `prep-sessions` resource branch), not here — this
module has no HTTP/path-parsing concerns of its own, same relationship
jobsuite_gemini.py has to jobsuite_api.py's `gemini` resource branch.
"""

import json
from datetime import datetime, timezone

import jobsuite_claude


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_error(message, status=400):
    return status, {"error": message}


def _row_to_dict(row):
    return {k: row[k] for k in row.keys()}


def _prep_session_row_to_json(row):
    d = _row_to_dict(row)
    for field in ("resume_structured", "job_structured"):
        d[field] = json.loads(d[field]) if d.get(field) else None
    for field in ("matched_skills", "missing_skills", "missing_evidence", "risks", "recommendations"):
        d[field] = json.loads(d[field]) if d.get(field) else []
    return d


def list_eligible_matches(conn):
    """Matches with a tailored CV ready to analyze: Processed status + cv_doc_id set."""
    rows = conn.execute(
        "SELECT * FROM matches WHERE status = 'Processed' AND cv_doc_id IS NOT NULL "
        "AND cv_doc_id != '' ORDER BY id DESC"
    ).fetchall()
    return 200, [_row_to_dict(r) for r in rows]


def create_prep_session(conn, match_id, config):
    match = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if not match:
        return _json_error("Match not found.", 404)
    if not match["cv_doc_id"]:
        return _json_error("This match has no tailored CV yet — send it to prep first.", 409)
    if not match["job_description"]:
        return _json_error("This match has no job description to analyze against.", 409)

    try:
        resume_text = jobsuite_claude.fetch_doc_text(config.get("doc_fetch_webhook"), match["cv_doc_id"])
        analysis = jobsuite_claude.run_ats_analysis(
            resume_text, match["job_description"], config.get("anthropic_api_key")
        )
    except Exception as e:
        return _json_error(str(e), 502)

    score = analysis["score"]
    subscores = score.get("subscores") or {}
    now = _now()
    cur = conn.execute(
        """INSERT INTO prep_sessions
           (match_id, resume_structured, job_structured, overall_score, skills_match,
            seniority_match, domain_match, experience_match, format_risk, matched_skills,
            missing_skills, missing_evidence, risks, recommendations, summary,
            created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            match_id,
            json.dumps(analysis["resume_structured"]), json.dumps(analysis["job_structured"]),
            score.get("overallScore"), subscores.get("skillsMatch"), subscores.get("seniorityMatch"),
            subscores.get("domainMatch"), subscores.get("experienceMatch"), subscores.get("formatRisk"),
            json.dumps(score.get("matchedSkills") or []), json.dumps(score.get("missingSkills") or []),
            json.dumps(score.get("missingEvidence") or []), json.dumps(score.get("risks") or []),
            json.dumps(score.get("recommendations") or []), score.get("summary"),
            now, now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM prep_sessions WHERE id = ?", (cur.lastrowid,)).fetchone()
    return 201, _prep_session_row_to_json(row)


def list_prep_sessions(conn, match_id):
    rows = conn.execute(
        "SELECT * FROM prep_sessions WHERE match_id = ? ORDER BY id DESC", (match_id,)
    ).fetchall()
    return 200, [_prep_session_row_to_json(r) for r in rows]


def get_prep_session(conn, session_id):
    row = conn.execute("SELECT * FROM prep_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        return _json_error("Prep session not found.", 404)
    return 200, _prep_session_row_to_json(row)
