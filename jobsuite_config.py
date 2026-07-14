"""Shared config loading — used by launch_launcher.py, jobsuite_gemini.py, and the
Streamlit app. Deliberately does NOT import pywebview (unlike launch_launcher.py),
so anything that just needs config.json values can import this safely.
"""

import json
import os
import sys

CONFIG_KEYS = (
    "gemini_api_key", "gdrive_webhook", "export_webhook",
    # Local-backend Make.com webhooks (see jobsuite_webhooks.py for what each does):
    # docgen_webhook        -> Pipeline 01 (New -> Processed: generates CV/cover letter)
    # drive_cleanup_webhook -> merged Pipelines 05/06/07, routed by an "action" field:
    #   move_to_applied   (Applied -> Migrated to Tracker)
    #   discard_docs      (Discarded -> Purged)
    #   archive_declined  (applications status = Application Declined)
    "docgen_webhook", "drive_cleanup_webhook",
    # JobPilot (Mode A: ATS Analyzer):
    # anthropic_api_key -> Claude, deliberately separate from Gemini so the ATS
    #                      re-score is an independent second opinion, not the same
    #                      model re-scoring its own earlier match.
    # doc_fetch_webhook -> a dedicated Make pipeline that fetches any Drive doc's
    #                      text by ID (unlike gdrive_webhook, which is hardcoded to
    #                      always fetch one fixed file — the base CV).
    "anthropic_api_key", "doc_fetch_webhook",
)


def exe_dir() -> str:
    """Next to the running .exe (or this file's folder, in dev mode). Used for things
    that are genuinely meant to be per-install (logs/, export_history.json) — anything
    that should be one shared copy (including config.json now) uses data_dir() instead."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def data_dir() -> str:
    """Where jobsuite.db / config.json / hunter-profiles.json / roles-config.json live —
    always the project's source root, whether running from source or from a built exe
    sitting in ./dist next to it, so there's never a second, diverging copy of real data
    or shared config. Falls back to exe_dir() if the source root can't be found (e.g. the
    exe was copied out on its own, with no source tree alongside it to point at)."""
    if getattr(sys, "frozen", False):
        exe_folder = os.path.dirname(sys.executable)
        parent = os.path.dirname(exe_folder)
        if os.path.basename(exe_folder).lower() == "dist" and os.path.isfile(os.path.join(parent, "jobsuite_db.py")):
            return parent
        return exe_folder
    return os.path.dirname(os.path.abspath(__file__))


def load_config() -> dict:
    config_path = os.path.join(data_dir(), "config.json")
    if not os.path.isfile(config_path):
        print(f"[INFO] No config.json found at {config_path} — using page defaults.")
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except json.JSONDecodeError as exc:
        print(f"[WARN] config.json is not valid JSON ({exc}) — using page defaults.")
        return {}
    config = {k: raw[k] for k in CONFIG_KEYS if k in raw and str(raw[k]).strip()}
    print(f"[INFO] Config loaded. Keys found: {', '.join(config.keys()) or '(none)'}")
    return config
