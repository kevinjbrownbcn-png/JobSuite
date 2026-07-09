"""/api/* request handling: CRUD over the matches and applications tables.

Kept transport-agnostic on purpose — dispatch() takes plain parsed values in and
returns a (status_code, json_serializable_body) tuple, so launch_launcher.py's
SuiteHandler owns all the actual HTTP I/O (reading the request body, writing the
response) and this module stays testable/callable without a real HTTP server.
"""

import json
import os
import re
from datetime import date, datetime, timezone

import jobsuite_gemini as gemini
import jobsuite_webhooks as webhooks
from jobsuite_config import data_dir
from jobsuite_db import get_connection

MATCH_STATUSES = [
    "Draft", "New", "Processed", "Applied", "Migrated to Tracker",
    "Discarded", "Purged", "N/A",
]

# The real primary-Tracker status list, confirmed against the live sheet.
APPLICATION_STATUSES = [
    "Application Sent", "Application Received", "Application under Review",
    "Follow-up", "Interview Arranged", "Interview held", "Offer made",
    "Offer Accepted", "Application Declined", "Not moving forward after interview",
    "Radio Silence",
]

# Front-end-facing header names for applications, matching the literal keys
# dashboard-api.js/dashboard-viewer.js already read off Sheet rows (row["Job Title"], etc.)
# so the existing render/filter/sort/KPI code needs no changes to consume this shape.
APPLICATIONS_HEADER_MAP = {
    "job_title": "Job Title",
    "company": "Company",
    "location": "Location",
    "applied_through": "Applied Through",
    "status": "Status",
    "job_url": "Job URL",
    "date_applied": "Date Applied",
    "notes": "Notes",
    "category": "Category",
    "posting_source": "Posting source",
    "first_response_date": "First Response Date",
    "last_status_update": "Last Status Update",
}

APPLICATION_EDITABLE_FIELDS = list(APPLICATIONS_HEADER_MAP.keys())
MATCH_EDITABLE_FIELDS = [
    "profile", "job_url", "job_description", "summary", "match_score", "notes",
    "applied_through", "posting_source",
]

# A Purged posting only resurfaces in scan results after this many days — long enough
# that it reads as a genuine repost rather than the scanner just re-finding something
# the user already rejected minutes/hours ago.
REPOST_THRESHOLD_DAYS = 30

# Jobs exported from the Audit page at or above this match score skip the manual
# "Send to Prep" click and go straight to doc generation.
AUTO_DOCGEN_THRESHOLD = 90

_MONTH_MAP = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
)}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row):
    return {k: row[k] for k in row.keys()}


def _json_error(message, status=400):
    return status, {"error": message}


def _parse_date(value):
    """Port of dashboard-api.js's parseDate — same '12/Mar/2026'-style handling,
    plus a plain ISO fallback. This is the current best approximation of the
    primary Tracker's real 'Response Time' formula, pending the user's exact rule."""
    if not value:
        return None
    text = str(value).strip()
    m = re.match(r"^(\d{1,2})[/\-]([A-Za-z]{3})[/\-](\d{4})", text)
    if m:
        month = _MONTH_MAP.get(m.group(2).lower())
        if month is None:
            return None
        try:
            return date(int(m.group(3)), month, int(m.group(1)))
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _format_duration_days(n):
    """Matches the sheet's day/week formatting exactly: '<14 days' as-is, else 'Nw Nd'."""
    if n < 14:
        return f"{n} day" if n == 1 else f"{n} days"
    weeks, days = divmod(n, 7)
    return f"{weeks}w" + (f" {days}d" if days > 0 else "")


def _compute_response_days(date_applied, first_response_date, last_status_update):
    """Raw day count backing Response Time's text — the actual elapsed time to the
    last known status change, once a real response exists. None if still pending or
    the dates don't parse. Used for the Average Response Time dashboard metric, so
    that averaging never has to re-parse the formatted "2w 4d"-style text back out."""
    applied = _parse_date(date_applied)
    first_response = _parse_date(first_response_date)
    if not applied or not first_response:
        return None
    last_status = _parse_date(last_status_update) or first_response
    if last_status == first_response:
        return (last_status - applied).days
    return (last_status - first_response).days


def _compute_response_time(date_applied, first_response_date, last_status_update):
    """Exact port of the primary Tracker's ARRAYFORMULA:
    - blank Date Applied -> ""
    - blank First Response Date -> "Pending response (N day(s))" counting from Date Applied
    - First Response Date == Last Status Update (no movement since first response)
      -> plain "N day(s)" from Date Applied to Last Status Update (NOT week-formatted —
      the sheet formula only applies the <14-day week conversion in the other branch)
    - otherwise -> week-formatted duration from First Response Date to Last Status Update
    """
    applied = _parse_date(date_applied)
    if not applied:
        return ""

    days = _compute_response_days(date_applied, first_response_date, last_status_update)
    if days is None:
        pending_days = (date.today() - applied).days
        suffix = "day" if pending_days == 1 else "days"
        return f"Pending response ({pending_days} {suffix})"

    first_response = _parse_date(first_response_date)
    last_status = _parse_date(last_status_update) or first_response
    if last_status == first_response:
        return f"{days} day" if days == 1 else f"{days} days"
    return _format_duration_days(days)


def _application_row_to_json(row):
    d = {"_id": row["id"]}
    for col, header in APPLICATIONS_HEADER_MAP.items():
        d[header] = row[col]
    d["Files archived?"] = "Yes" if row["files_archived"] else ""
    d["Response Time"] = _compute_response_time(
        row["date_applied"], row["first_response_date"], row["last_status_update"]
    )
    d["_response_days"] = _compute_response_days(
        row["date_applied"], row["first_response_date"], row["last_status_update"]
    )
    return d


def _match_row_to_json(row):
    d = _row_to_dict(row)
    d["skills_gaps"] = json.loads(d["skills_gaps"]) if d.get("skills_gaps") else []
    d["preparation_material"] = json.loads(d["preparation_material"]) if d.get("preparation_material") else []
    return d


# ------------------------------------------------------------------- posting sources

def add_posting_source(body):
    """Appends a new Posting Source to hunter-profiles.json if it's not already there
    (case-insensitive) — called whenever the Manual Audit "Other" field is used, so the
    dropdown grows on its own instead of needing a code change each time. No DB involved,
    just the static JSON config file both the desktop UI and Streamlit read from."""
    source = (body.get("source") or "").strip()
    if not source:
        return _json_error("No source provided.")

    path = os.path.join(data_dir(), "hunter-profiles.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            profiles = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        profiles = {}

    sources = profiles.setdefault("postingSources", [])
    if not any(s.lower() == source.lower() for s in sources):
        sources.append(source)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(profiles, fh, indent=4, ensure_ascii=False)

    return 200, {"postingSources": sources}


# --------------------------------------------------------------------------- matches

def _filter_scanned_jobs(conn, jobs):
    """Cross-references freshly scanned jobs against every existing match signature
    (job_title + company, case-insensitive) so postings already sitting somewhere in
    the pipeline don't resurface as "new". A signature that's Purged everywhere it
    appears is the one exception — it's let back through, tagged `_reposted`, once
    REPOST_THRESHOLD_DAYS have passed since it was purged (the "reappeared" case)."""
    existing = {}
    for row in conn.execute("SELECT job_title, company, status, updated_at FROM matches"):
        title = (row["job_title"] or "").strip().lower()
        company = (row["company"] or "").strip().lower()
        if not title or not company:
            continue
        existing.setdefault((title, company), []).append((row["status"], row["updated_at"]))

    now = datetime.now(timezone.utc)
    kept = []
    for job in jobs:
        title = (job.get("job_title") or "").strip().lower()
        company = (job.get("company") or "").strip().lower()
        rows = existing.get((title, company)) if title and company else None
        if not rows:
            kept.append(job)
            continue

        if any(status != "Purged" for status, _ in rows):
            continue  # still active somewhere in the pipeline — never re-suggest

        purge_dates = [datetime.fromisoformat(ts) for _, ts in rows if ts]
        latest_purge = max(purge_dates) if purge_dates else None
        if latest_purge and (now - latest_purge).days < REPOST_THRESHOLD_DAYS:
            continue

        job["_reposted"] = True
        kept.append(job)

    return kept


def list_matches(conn, query):
    status_filter = (query.get("status") or [None])[0]
    if status_filter:
        rows = conn.execute(
            "SELECT * FROM matches WHERE status = ? ORDER BY id DESC", (status_filter,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM matches ORDER BY id DESC").fetchall()
    return 200, [_match_row_to_json(r) for r in rows]


def create_matches(conn, body, config):
    jobs = body.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        return _json_error("Request body must include a non-empty 'jobs' array.")

    now = _now()
    inserted = []
    high_score_ids = []
    for job in jobs:
        title = (job.get("job_title") or "").strip()
        company = (job.get("company") or "").strip()
        if not title or not company:
            continue
        gaps = job.get("skills_gaps") or []
        prep = job.get("resources") or job.get("preparation_material") or []
        cur = conn.execute(
            """INSERT INTO matches
               (profile, job_title, company, location, job_url, job_description, summary,
                match_score, skills_gaps, preparation_material, notes, applied_through,
                posting_source, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job.get("profile"), title, company, job.get("location"),
                job.get("link") or job.get("job_url"), job.get("description"), job.get("summary"),
                job.get("match_score"), json.dumps(gaps), json.dumps(prep), job.get("notes"),
                job.get("applied_through"), job.get("posting_source"),
                "Draft", now, now,
            ),
        )
        match_id = cur.lastrowid
        inserted.append(match_id)

        try:
            score = float(job.get("match_score"))
        except (TypeError, ValueError):
            score = None
        if score is not None and score >= AUTO_DOCGEN_THRESHOLD:
            high_score_ids.append(match_id)

    if not inserted:
        return _json_error("No valid jobs in payload (job_title and company are required).")

    conn.commit()

    # Skip the manual "Send to Prep" click for high-confidence matches — reuses
    # update_match's own "New" transition so doc generation, the Processed/Draft
    # outcome, and retry semantics on failure are identical to clicking the button
    # by hand (a failed webhook just leaves the row at Draft, same as always).
    auto_sent, auto_failed = [], []
    for match_id in high_score_ids:
        status, resp = update_match(conn, match_id, {"status": "New"}, config)
        if status == 200:
            auto_sent.append(match_id)
        else:
            auto_failed.append({"id": match_id, "error": resp.get("error")})

    response = {"inserted_ids": inserted, "count": len(inserted)}
    if auto_sent:
        response["_auto_docgen_sent"] = auto_sent
    if auto_failed:
        response["_auto_docgen_failed"] = auto_failed
    return 201, response


def update_match(conn, match_id, body, config):
    row = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if not row:
        return _json_error("Match not found.", 404)

    set_clauses, params = [], []
    for f in MATCH_EDITABLE_FIELDS:
        if f in body:
            set_clauses.append(f"{f} = ?")
            params.append(body[f])

    new_status = body.get("status")
    warning = None

    # "New" and "Discarded" must be retriable even when the row is already sitting at
    # that status — that's exactly what happens when their webhook call failed last
    # time (the status is set eagerly for Discarded, and never advances past New/stays
    # at Processed on failure, so a plain "!=" guard would silently no-op a retry).
    is_status_change = bool(new_status) and (
        new_status != row["status"] or new_status in ("New", "Discarded")
    )

    if is_status_change:
        if new_status not in MATCH_STATUSES:
            return _json_error(f"Invalid status '{new_status}'. Must be one of {MATCH_STATUSES}.")

        if new_status == "Applied" and row["status"] == "Migrated to Tracker":
            return _json_error("This match has already been migrated to the tracker.", 409)

        if new_status == "New":
            # Pipeline 01: generates the tailored CV/cover letter from GDrive templates.
            result = webhooks.fire_docgen(config.get("docgen_webhook"), _row_to_dict(row))
            if not result.get("ok"):
                return _json_error(f"Doc generation failed: {result.get('error')}", 502)
            set_clauses.append("status = ?")
            params.append("Processed")

        elif new_status == "Applied":
            # Pipeline 06 (isApplied route): finds the generated CV/cover letter and
            # moves them into the '_applied' Drive folder. Only once that succeeds does
            # the app create the corresponding applications row and promote the match —
            # the old Sheet-to-Sheet copy step has no local equivalent to call out for,
            # since both "sheets" are this same database now.
            result = webhooks.fire_move_to_applied(config.get("drive_cleanup_webhook"), _row_to_dict(row))
            if not result.get("ok"):
                return _json_error(f"Moving generated docs to _applied failed: {result.get('error')}", 502)

            now = _now()
            conn.execute(
                """INSERT INTO applications
                   (source_match_id, job_title, company, status, job_url, date_applied,
                    category, applied_through, posting_source, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    match_id, row["job_title"], row["company"], "Application Sent",
                    row["job_url"], date.today().isoformat(), row["profile"],
                    row["applied_through"], row["posting_source"], now, now,
                ),
            )
            set_clauses.append("status = ?")
            params.append("Migrated to Tracker")

        elif new_status == "Discarded":
            # Persist the decision locally regardless of Drive cleanup outcome — the
            # user has decided either way; the doc trash-and-purge is best-effort and
            # retryable, unlike New/Applied which must succeed before the status moves on.
            set_clauses.append("status = ?")
            params.append("Discarded")

        else:
            set_clauses.append("status = ?")
            params.append(new_status)

    if not set_clauses:
        return _json_error("No recognized fields to update.")

    set_clauses.append("updated_at = ?")
    params.append(_now())
    params.append(match_id)
    conn.execute(f"UPDATE matches SET {', '.join(set_clauses)} WHERE id = ?", params)
    conn.commit()

    updated = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()

    if new_status == "Discarded":
        # Pipeline 06 (isDiscarded route) / Pipeline 05: finds and trashes the generated
        # docs, since this match will never be applied to.
        result = webhooks.fire_discard_docs(config.get("drive_cleanup_webhook"), _row_to_dict(updated))
        if result.get("ok"):
            conn.execute("UPDATE matches SET status = 'Purged' WHERE id = ?", (match_id,))
            conn.commit()
            updated = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
        else:
            warning = result.get("error")

    response = _match_row_to_json(updated)
    if warning:
        response["_discard_warning"] = warning
    return 200, response


def delete_match(conn, match_id):
    row = conn.execute("SELECT id FROM matches WHERE id = ?", (match_id,)).fetchone()
    if not row:
        return _json_error("Match not found.", 404)
    conn.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    conn.commit()
    return 200, {"deleted": match_id}


# ----------------------------------------------------------------------- applications

def list_applications(conn):
    # Ascending (oldest first) to match the old Sheet's natural top-to-bottom row order —
    # dashboard-api.js already does its own .reverse() on top of this to prioritize new entries.
    rows = conn.execute("SELECT * FROM applications ORDER BY id ASC").fetchall()
    return 200, [_application_row_to_json(r) for r in rows]


def get_application(conn, app_id):
    row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    if not row:
        return _json_error("Application not found.", 404)
    return 200, _application_row_to_json(row)


def create_application(conn, body):
    title = (body.get("job_title") or "").strip()
    company = (body.get("company") or "").strip()
    if not title or not company:
        return _json_error("job_title and company are required.")

    now = _now()
    values = {f: body.get(f) for f in APPLICATION_EDITABLE_FIELDS}
    values["job_title"] = title
    values["company"] = company
    if not values.get("status"):
        values["status"] = "Application Sent"

    cols = list(values.keys())
    cur = conn.execute(
        f"""INSERT INTO applications ({', '.join(cols)}, created_at, updated_at)
            VALUES ({', '.join('?' for _ in cols)}, ?, ?)""",
        [*values.values(), now, now],
    )
    conn.commit()

    row = conn.execute("SELECT * FROM applications WHERE id = ?", (cur.lastrowid,)).fetchone()
    return 201, _application_row_to_json(row)


def update_application(conn, app_id, body, config):
    row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    if not row:
        return _json_error("Application not found.", 404)

    set_clauses, params = [], []
    for f in APPLICATION_EDITABLE_FIELDS:
        if f in body:
            set_clauses.append(f"{f} = ?")
            params.append(body[f])

    new_status = body.get("status")
    if new_status and new_status != row["status"]:
        # First Response Date and Last Status Update are only ever set once the status
        # first moves away from "Application Sent" — after that, further status changes
        # only bump Last Status Update, per the real sheet's data-entry convention.
        today_iso = date.today().isoformat()
        if row["status"] == "Application Sent" and not row["first_response_date"]:
            if "first_response_date" not in body:
                set_clauses.append("first_response_date = ?")
                params.append(today_iso)
        if "last_status_update" not in body:
            set_clauses.append("last_status_update = ?")
            params.append(today_iso)

    if not set_clauses:
        return _json_error("No recognized fields to update.")

    now = _now()
    set_clauses.append("updated_at = ?")
    params.append(now)
    params.append(app_id)
    conn.execute(f"UPDATE applications SET {', '.join(set_clauses)} WHERE id = ?", params)
    conn.commit()

    updated = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()

    warning = None
    if "status" in body:
        # Persisted locally regardless of webhook outcome — manual CRM entry shouldn't
        # be blocked by a Make outage. Pipeline 07 only ever triggers on the literal
        # "Application Declined" status; nothing else moves files in the real blueprint.
        result = webhooks.fire_archive_declined(config.get("drive_cleanup_webhook"), _row_to_dict(updated))
        if result.get("ok") and not result.get("skipped"):
            conn.execute("UPDATE applications SET files_archived = 1 WHERE id = ?", (app_id,))
            conn.commit()
            updated = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        elif not result.get("ok"):
            warning = result.get("error")

    response = _application_row_to_json(updated)
    if warning:
        response["_archive_warning"] = warning
    return 200, response


# --------------------------------------------------------------------------- dispatch

def dispatch_gemini(method, action, body, config):
    """Handles /api/gemini/* — no DB connection needed, and these calls can block for
    a while (external Gemini/web requests), so they're kept out of dispatch()'s
    conn-open/close block entirely."""
    if method != "POST":
        return _json_error("Not found.", 404)

    api_key = config.get("gemini_api_key")
    gdrive_webhook = config.get("gdrive_webhook")

    try:
        if action == "scan":
            jobs = gemini.scan_web_for_jobs(
                body.get("roles") or [], body.get("location", ""), body.get("time_window", ""),
                body.get("focus", ""), api_key, gdrive_webhook,
            )
            conn = get_connection()
            try:
                jobs = _filter_scanned_jobs(conn, jobs)
            finally:
                conn.close()
            return 200, jobs

        if action == "analyze-text":
            job = gemini.analyze_manual_text(
                body.get("description", ""), body.get("profile", ""),
                body.get("title", ""), body.get("company", ""),
                api_key, gdrive_webhook,
            )
            return 200, job

        if action == "analyze-url":
            job = gemini.analyze_manual_url(body.get("url", ""), body.get("profile", ""), api_key, gdrive_webhook)
            return 200, job

        if action == "analyze-hub":
            jobs = gemini.analyze_careers_hub(body.get("url", ""), body.get("profile", ""), api_key)
            conn = get_connection()
            try:
                jobs = _filter_scanned_jobs(conn, jobs)
            finally:
                conn.close()
            return 200, jobs
    except Exception as e:
        return _json_error(str(e), 502)

    return _json_error("Not found.", 404)


def dispatch(method, path, query, body, config):
    body = body or {}
    parts = [p for p in path.split("/") if p]  # e.g. ['api', 'matches', '5']
    if len(parts) < 2 or parts[0] != "api":
        return _json_error("Not found.", 404)

    resource = parts[1]
    action = parts[2] if len(parts) > 2 else None

    if resource == "gemini":
        return dispatch_gemini(method, action, body, config)

    if resource == "posting-sources":
        if method == "POST":
            return add_posting_source(body)
        return _json_error("Not found.", 404)

    resource_id = int(action) if action and action.isdigit() else None

    conn = get_connection()
    try:
        if resource == "matches":
            if method == "GET" and resource_id is None:
                return list_matches(conn, query)
            if method == "POST" and resource_id is None:
                return create_matches(conn, body, config)
            if method == "PATCH" and resource_id is not None:
                return update_match(conn, resource_id, body, config)
            if method == "DELETE" and resource_id is not None:
                return delete_match(conn, resource_id)

        elif resource == "applications":
            if method == "GET" and resource_id is None:
                return list_applications(conn)
            if method == "GET" and resource_id is not None:
                return get_application(conn, resource_id)
            if method == "POST" and resource_id is None:
                return create_application(conn, body)
            if method == "PATCH" and resource_id is not None:
                return update_application(conn, resource_id, body, config)

        return _json_error("Not found.", 404)
    finally:
        conn.close()
