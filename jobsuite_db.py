"""SQLite schema, connection helper, and initialization for JobSuite's local data store.

This replaces both Google Sheets (the Match tracker staging sheet and the primary
application Tracker) as the single source of truth for the app.
"""

import os
import sqlite3

from jobsuite_config import data_dir

DB_PATH = os.path.join(data_dir(), "jobsuite.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    profile               TEXT,
    job_title             TEXT NOT NULL,
    company               TEXT NOT NULL,
    location              TEXT,
    job_url               TEXT,
    job_description       TEXT,
    summary               TEXT,
    match_score           INTEGER,
    skills_gaps           TEXT,
    preparation_material  TEXT,
    notes                 TEXT,
    applied_through       TEXT,
    posting_source        TEXT,
    status                TEXT NOT NULL DEFAULT 'Draft'
                          CHECK(status IN ('Draft','New','Processed','Applied',
                                           'Migrated to Tracker','Discarded','Purged','N/A')),
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);

CREATE TABLE IF NOT EXISTS applications (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    source_match_id      INTEGER REFERENCES matches(id),
    job_title            TEXT NOT NULL,
    company              TEXT NOT NULL,
    location             TEXT,
    applied_through      TEXT,
    status               TEXT NOT NULL DEFAULT 'Application Sent',
    job_url              TEXT,
    date_applied         TEXT,
    notes                TEXT,
    category             TEXT,
    posting_source       TEXT,
    first_response_date  TEXT,
    last_status_update   TEXT,
    files_archived       INTEGER NOT NULL DEFAULT 0,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_source_match ON applications(source_match_id);

-- JobPilot Mode A (ATS Analyzer): one row per Claude-scored fit analysis of a match's
-- tailored CV against its job description. Kept separate from `applications` (which
-- means something else — the real Tracker) to avoid the naming clash in the original
-- JobPilot spec.
CREATE TABLE IF NOT EXISTS prep_sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id            INTEGER NOT NULL REFERENCES matches(id),
    resume_structured   TEXT,
    job_structured      TEXT,
    overall_score       INTEGER,
    skills_match        INTEGER,
    seniority_match     INTEGER,
    domain_match        INTEGER,
    experience_match    INTEGER,
    format_risk         INTEGER,
    matched_skills      TEXT,
    missing_skills      TEXT,
    missing_evidence    TEXT,
    risks               TEXT,
    recommendations     TEXT,
    summary             TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prep_sessions_match ON prep_sessions(match_id);
"""


def get_connection() -> sqlite3.Connection:
    """Fresh short-lived connection per request — safe under ThreadingHTTPServer
    without sharing a connection object across threads."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Columns added after the table was first created — CREATE TABLE IF NOT EXISTS won't
# retrofit these onto an existing database, so init_db() adds any that are missing.
MATCHES_MIGRATIONS = [
    ("applied_through", "TEXT"),
    ("posting_source", "TEXT"),
    ("is_workday", "INTEGER NOT NULL DEFAULT 0"),
    # Populated from Pipeline 01's docgen webhook response once it returns them —
    # lets JobPilot pull the actual tailored CV/cover letter text for ATS analysis.
    ("cv_doc_id", "TEXT"),
    ("cv_doc_url", "TEXT"),
    ("cover_letter_doc_id", "TEXT"),
    ("cover_letter_doc_url", "TEXT"),
]


def _migrate(conn) -> None:
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(matches)")}
    for col, col_type in MATCHES_MIGRATIONS:
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE matches ADD COLUMN {col} {col_type}")


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()
