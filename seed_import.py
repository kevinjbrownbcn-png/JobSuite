"""One-time seed import: load JSON exports of the two legacy Google Sheets into jobsuite.db.

Usage:
    python seed_import.py matches_export.json applications_export.json

Each JSON file is expected to be a flat array of row objects keyed by the sheet's
literal column headers — the same shape produced by the user's Excel-to-JSON export
tool. That export tool is pandas-based, so exported rows carry pandas' null markers
(float NaN for blank cells, the literal string "NaT" for blank datetimes) and a couple
of pandas-artifact columns (e.g. "_ID", "Unnamed: 15") — all cleaned/ignored here.

All dates are normalized to ISO 'YYYY-MM-DD' on the way in, regardless of whether the
source cell was "12/Mar/2026", "2026-03-12 00:00:00", or a full timestamp — this keeps
every date field in one consistent format going forward, matching what the running app
writes itself (see jobsuite_api.py's Applied-transition and status-change auto-stamping).

Not part of the running app. Run manually, once. Safe to re-run against a fresh
jobsuite.db (it does not de-duplicate against existing rows, so don't run it twice
against the same live database without deleting jobsuite.db first).
"""

import argparse
import json
import math
import sys

import jobsuite_db
from jobsuite_api import APPLICATIONS_HEADER_MAP, MATCH_STATUSES, _parse_date

# Column F's header text in the Match tracker sheet holds the lifecycle status
# (Draft / New / Processed / Applied / Migrated to Tracker / Discarded / Purged / N/A).
MATCHES_HEADER_MAP = {
    "Profile": "profile",
    "Job Title": "job_title",
    "Company": "company",
    "Job URL": "job_url",
    "Job Description": "job_description",
    "Migrated to Tracker": "status",
    "Match Score": "match_score",
    "Skills Gaps": "skills_gaps",
    "Preparation Material": "preparation_material",
    "Notes": "notes",
}

# header -> column, inverse of the applications serialization map in jobsuite_api.py
# (kept as the single source of truth so the seed script and the live API never drift apart)
APPLICATIONS_IMPORT_MAP = {header: col for col, header in APPLICATIONS_HEADER_MAP.items()}

DATE_COLUMNS = {"date_applied", "first_response_date", "last_status_update"}


def _clean(value):
    """Normalize pandas-exported NaN/NaT artifacts to None; strip strings."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped in ("", "NaT", "nan", "NaN"):
            return None
        return stripped
    return value


def _to_iso_date(value):
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed else None


def _as_list(value):
    """Skills Gaps is free-form prose in the real data (e.g. a comma-joined sentence) —
    kept as a single list item rather than split. Preparation Material is newline-separated
    in the real data, so that one gets split into real array entries."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    text = str(value)
    if "\n" in text:
        return [line.strip() for line in text.split("\n") if line.strip()]
    return [text]


def import_matches(conn, rows):
    inserted = 0
    bad_status_count = 0

    for i, row in enumerate(rows):
        values = {col: _clean(row.get(header)) for header, col in MATCHES_HEADER_MAP.items() if header in row}

        title = (values.get("job_title") or "").strip()
        company = (values.get("company") or "").strip()
        if not title or not company:
            print(f"[matches] Skipping row {i}: missing Job Title/Company.")
            continue

        status = values.get("status") or "Draft"
        if status not in MATCH_STATUSES:
            print(f"[matches] Row {i}: unrecognized status {status!r}, importing as 'N/A' instead.")
            status = "N/A"
            bad_status_count += 1

        match_score = values.get("match_score")
        match_score = int(match_score) if match_score is not None else None

        skills_gaps = json.dumps(_as_list(values.get("skills_gaps")))
        prep = json.dumps(_as_list(values.get("preparation_material")))

        conn.execute(
            """INSERT INTO matches
               (profile, job_title, company, job_url, job_description,
                match_score, skills_gaps, preparation_material, notes, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?, datetime('now'), datetime('now'))""",
            (
                values.get("profile"), title, company, values.get("job_url"),
                values.get("job_description"), match_score,
                skills_gaps, prep, values.get("notes"), status,
            ),
        )
        inserted += 1

    conn.commit()
    print(f"[matches] Inserted {inserted} of {len(rows)} row(s).")
    if bad_status_count:
        print(f"[matches] {bad_status_count} row(s) had an unrecognized status value — check those manually.")


def import_applications(conn, rows):
    inserted = 0
    date_failures = []

    for i, row in enumerate(rows):
        values = {col: _clean(row.get(header)) for header, col in APPLICATIONS_IMPORT_MAP.items() if header in row}

        title = (values.get("job_title") or "").strip()
        company = (values.get("company") or "").strip()
        if not title or not company:
            print(f"[applications] Skipping row {i}: missing Job Title/Company.")
            continue

        for col in DATE_COLUMNS:
            raw = values.get(col)
            if raw:
                iso = _to_iso_date(raw)
                if iso is None:
                    date_failures.append((i, col, raw))
                values[col] = iso

        files_archived_raw = _clean(row.get("Files archived?"))
        files_archived = 1 if str(files_archived_raw or "").strip().lower() == "yes" else 0

        cols = list(values.keys())
        conn.execute(
            f"""INSERT INTO applications
                ({', '.join(cols)}, files_archived, created_at, updated_at)
                VALUES ({', '.join('?' for _ in cols)}, ?, datetime('now'), datetime('now'))""",
            [*values.values(), files_archived],
        )
        inserted += 1

    conn.commit()
    print(f"[applications] Inserted {inserted} of {len(rows)} row(s).")

    if date_failures:
        print(f"[applications] WARNING: {len(date_failures)} date value(s) did not parse — "
              f"stored as blank, check these before trusting Response Time output:")
        for i, col, raw in date_failures[:20]:
            print(f"    row {i}: {col} = {raw!r}")
        if len(date_failures) > 20:
            print(f"    ...and {len(date_failures) - 20} more.")


def main():
    parser = argparse.ArgumentParser(description="One-time seed import for JobSuite's local database.")
    parser.add_argument("matches_json", help="Path to the Match tracker sheet exported as JSON.")
    parser.add_argument("applications_json", help="Path to the primary Tracker sheet exported as JSON.")
    args = parser.parse_args()

    jobsuite_db.init_db()
    conn = jobsuite_db.get_connection()
    try:
        with open(args.matches_json, "r", encoding="utf-8") as fh:
            matches_rows = json.load(fh)
        with open(args.applications_json, "r", encoding="utf-8") as fh:
            applications_rows = json.load(fh)

        if not isinstance(matches_rows, list) or not isinstance(applications_rows, list):
            print("[ERROR] Both JSON files must contain a flat array of row objects.")
            sys.exit(1)

        import_matches(conn, matches_rows)
        import_applications(conn, applications_rows)
    finally:
        conn.close()

    print(f"\nDone. Database at: {jobsuite_db.DB_PATH}")


if __name__ == "__main__":
    main()
