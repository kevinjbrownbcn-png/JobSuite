"""Small shared helpers for the Streamlit pages — kept separate from jobsuite_api.py
since these are UI-layer concerns (JSON config loading, role categorization for the
Dashboard charts), not part of the transport-agnostic API/DB layer.
"""

import json
import os

from jobsuite_config import data_dir


def load_json_config(filename: str) -> dict:
    path = os.path.join(data_dir(), filename)
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def categorize_role(job_title: str, role_map: dict) -> str:
    """Mirrors dashboard-viewer.js's ROLE_MAPPING_DICTIONARY keyword matching."""
    title_lower = (job_title or "").lower()
    for role_type, keywords in role_map.items():
        if any(kw.lower() in title_lower for kw in keywords):
            return role_type
    return "Uncategorized / Other"
