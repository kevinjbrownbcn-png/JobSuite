"""Outbound webhook helpers for the Make.com scenarios that stay in the picture.

Based on the real blueprints (Pipelines 01/02/05/06/07):
  - Pipeline 02 (CV fetch) is untouched — still called directly from hunter-config.js,
    nothing to do with the local API.
  - Pipeline 03 (export -> Match tracker sheet) is retired — replaced by a direct local
    DB write (see hunter-exporter.js -> POST /api/matches).
  - Pipeline 01 (doc generation) keeps its GPT/Docs-template logic, but its trigger flips
    from "watch the Sheet for F=New" to a webhook the app calls and blocks on. Fires on
    matches status -> 'New'. On success, match status -> 'Processed'.
  - Pipelines 05, 06 (both routes), and 07 are merged into one Make scenario/webhook
    (Pipeline 05 and Pipeline 06's isDiscarded route were near-duplicates of each other
    anyway). One shared `drive_cleanup_webhook` URL, routed by an `action` field in the
    payload instead of three separate webhooks:
      - action="move_to_applied": finds the generated CV/cover letter and moves them into
        the '_applied' Drive folder. Fires on matches status -> 'Applied'. On success, the
        app inserts the corresponding `applications` row itself (the old Sheet-to-Sheet
        copy has no local equivalent to call out for — it's just a DB insert now) and sets
        match status -> 'Migrated to Tracker'.
      - action="discard_docs": finds and trashes the generated docs for a match that's
        being discarded before ever being applied to. Fires on matches status ->
        'Discarded'. On success, match status -> 'Purged'.
      - action="archive_declined": moves '_applied' docs to '_declined' and sets Files
        archived=Yes. Fires on applications status -> 'Application Declined' specifically
        (the only status that triggers Drive archiving per the real blueprint — not a
        3-way bucket).
"""

import json

try:
    import requests
except ImportError:  # pragma: no cover - degrades gracefully, same pattern as LoggerAPI
    requests = None

DEFAULT_TIMEOUT = 60

ARCHIVE_TRIGGER_STATUS = "Application Declined"


def _post_json(url, payload, timeout=DEFAULT_TIMEOUT):
    if not url:
        return {"ok": False, "error": "No webhook URL configured."}
    if requests is None:
        return {"ok": False, "error": "The 'requests' package is not installed."}
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        try:
            body = resp.json()
        except (ValueError, json.JSONDecodeError):
            body = {}
        return {"ok": True, "response": body}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": str(e)}


def fire_docgen(webhook_url, match_row):
    """Pipeline 01: New -> Processed. Generates the tailored CV/cover letter.

    `notes` carries user-written instructions for this specific application (e.g.
    "posting says on-site/hybrid — request remote consideration in the cover letter")
    for the scenario's drafting step to take into account. It's inert until Pipeline
    01's own prompt is updated to read and act on it — this just gets it there.
    """
    payload = {
        "profile": match_row.get("profile"),
        "job_title": match_row.get("job_title"),
        "company": match_row.get("company"),
        "job_url": match_row.get("job_url"),
        "job_description": match_row.get("job_description"),
        "notes": match_row.get("notes"),
        "is_workday": bool(match_row.get("is_workday")),
    }
    return _post_json(webhook_url, payload)


def fire_move_to_applied(webhook_url, match_row):
    """action=move_to_applied: finds 'Kevin Brown - {title} - {company} - CV/Cover
    Letter' in Generated_Outputs and moves them into the '_applied' folder."""
    payload = {
        "action": "move_to_applied",
        "job_title": match_row.get("job_title"),
        "company": match_row.get("company"),
    }
    return _post_json(webhook_url, payload)


def fire_discard_docs(webhook_url, match_row):
    """action=discard_docs: finds and trashes the generated docs for a match that's
    being discarded before ever being applied to."""
    payload = {
        "action": "discard_docs",
        "job_title": match_row.get("job_title"),
        "company": match_row.get("company"),
    }
    return _post_json(webhook_url, payload)


def fire_archive_declined(webhook_url, application_row):
    """action=archive_declined: moves '_applied' docs to '_declined' and sets Files
    archived=Yes. Only fires when status is exactly 'Application Declined' — the real
    blueprint has no equivalent trigger for any other status."""
    if application_row.get("status") != ARCHIVE_TRIGGER_STATUS:
        return {"ok": True, "skipped": True}
    payload = {
        "action": "archive_declined",
        "job_title": application_row.get("job_title"),
        "company": application_row.get("company"),
    }
    return _post_json(webhook_url, payload)
