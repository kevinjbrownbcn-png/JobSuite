#!/usr/bin/env python3
"""
JobSuite — Unified Launcher
============================
Opens launcher.html as a native desktop window.
Reads API keys and webhook URLs from config.json (next to the .exe).
All three pages (launcher.html, dashboard.html, hunter.html) are served
from the same local HTTP server, so navigation between them works seamlessly.

Requirements (install once):
    pip install pywebview

Usage:
    python launch_launcher.py
    python launch_launcher.py --width 1400 --height 900
    python launch_launcher.py --debug
"""

import argparse
import datetime
import json
import os
import sys
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import jobsuite_api
import jobsuite_db
from jobsuite_config import data_dir, exe_dir, load_config

# Served from data_dir() instead of the static bundle — these are user-editable config
# (e.g. Posting Source additions), not fixed app code, so a frozen exe must read/write
# the same live copy every run rather than a temp extraction that resets on each launch.
DATA_JSON_FILES = ("hunter-profiles.json", "roles-config.json")


# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------
try:
    import webview
except ImportError:
    print(
        "\n[ERROR] pywebview is not installed.\n"
        "Install it with:\n\n"
        "    pip install pywebview\n\n"
        "On Linux you may also need one of these GUI back-ends:\n"
        "    pip install pywebview[gtk]   # GTK / GNOME\n"
        "    pip install pywebview[qt]    # Qt5/Qt6\n"
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Logger API — exposes file logging + hub scanning to JS via pywebview js_api
# ---------------------------------------------------------------------------

class LoggerAPI:
    """Mounts onto window.pywebview.api so JS can write error logs and run hub scans."""

    def __init__(self, config: dict):
        self._config = config

    def write_error_log(self, log_title, exception_msg, technical_payload):
        try:
            logs_dir = os.path.join(exe_dir(), "logs")
            os.makedirs(logs_dir, exist_ok=True)

            timestamp  = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            safe_title = "".join(
                c for c in log_title if c.isalnum() or c in (" ", "_", "-")
            ).strip().replace(" ", "_")

            filename = f"error_{timestamp}_{safe_title}.txt"
            log_path = os.path.join(logs_dir, filename)

            with open(log_path, "w", encoding="utf-8") as fh:
                fh.write("=" * 60 + "\n")
                fh.write("JOBSUITE — PIPELINE EXCEPTION LOG\n")
                fh.write("=" * 60 + "\n")
                fh.write(f"Timestamp      : {datetime.datetime.now().isoformat()}\n")
                fh.write(f"Error Domain   : {log_title}\n")
                fh.write(f"Exception Type : {exception_msg}\n")
                fh.write("-" * 60 + "\n")
                fh.write("TECHNICAL DEBUG CONTEXT / RESPONSE PAYLOAD:\n")
                fh.write("-" * 60 + "\n")
                fh.write(str(technical_payload))
                fh.write("\n" + "=" * 60 + "\n")

            print(f"[INFO] Error log written to: {log_path}")
            return True
        except Exception as err:
            print(f"[ERROR] Failed to write error log: {err}")
            return False

    def save_to_local_json_file(self, fresh_jobs_json):
        file_path = os.path.abspath(os.path.join(exe_dir(), "export_history.json"))
        try:
            new_jobs = json.loads(fresh_jobs_json)
            if not isinstance(new_jobs, list):
                new_jobs = [new_jobs]

            existing_history = []
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                        if isinstance(data, list):
                            existing_history = data
                except Exception:
                    existing_history = []

            archived_at = datetime.datetime.utcnow().isoformat() + "Z"
            for job in new_jobs:
                job["offline_archived_at"] = archived_at
                existing_history.append(job)

            with open(file_path, "w", encoding="utf-8") as fh:
                json.dump(existing_history, fh, indent=4, ensure_ascii=False)

            print(f"[INFO] {len(new_jobs)} job(s) saved to: {file_path}")
            return json.dumps({"status": "success", "path": file_path, "count": len(new_jobs)})

        except Exception as err:
            print(f"[ERROR] save_to_local_json_file failed: {err}")
            self.write_error_log("Python_Local_File_Save_Fault", str(err), fresh_jobs_json)
            return json.dumps({"status": "error", "message": str(err)})

    def check_url_status(self, url: str) -> str:
        """HEAD-checks a URL and returns its HTTP status. Called per job card after render."""
        try:
            import requests
            resp = requests.head(
                url, timeout=8, allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            return json.dumps({"status": resp.status_code, "ok": resp.status_code < 400})
        except Exception as e:
            label = "timeout" if "timeout" in type(e).__name__.lower() or "timed out" in str(e).lower() else "error"
            print(f"[URL-CHECK] {label} — {url}: {e}")
            return json.dumps({"status": 0, "error": label})

# ---------------------------------------------------------------------------
# Local HTTP server — serves the entire JobSuite directory
# ---------------------------------------------------------------------------

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js":   "application/javascript",
    ".mjs":  "application/javascript",
    ".css":  "text/css",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".svg":  "image/svg+xml",
    ".ico":  "image/x-icon",
    ".json": "application/json",
}


class SuiteHandler(BaseHTTPRequestHandler):
    """Serves all files in the JobSuite root."""

    root_dir  = ""
    config    = {}

    def log_message(self, fmt, *args):
        print(f"[SERVER] {self.address_string()} - {fmt % args}")

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path.startswith("/api/"):
            self._handle_api("GET")
            return

        path = parsed.path

        # Default to launcher.html for root requests
        if path in ("/", ""):
            path = "/launcher.html"

        if path.lstrip("/") in DATA_JSON_FILES:
            base_dir = data_dir()
        else:
            base_dir = self.root_dir

        file_path = os.path.normpath(os.path.join(base_dir, path.lstrip("/")))

        # Safety: prevent directory traversal outside the intended root
        if not file_path.startswith(base_dir):
            self.send_error(403)
            return

        if not os.path.isfile(file_path):
            print(f"[SERVER] 404 not found: {file_path}")
            self.send_error(404)
            return

        ext  = os.path.splitext(file_path)[1].lower()
        mime = MIME_TYPES.get(ext, "application/octet-stream")

        with open(file_path, "rb") as fh:
            body = fh.read()

        self.send_response(200)
        self.send_header("Content-Type",   mime)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self._dispatch_api_only("POST")

    def do_PATCH(self):
        self._dispatch_api_only("PATCH")

    def do_DELETE(self):
        self._dispatch_api_only("DELETE")

    def _dispatch_api_only(self, method):
        if not urlparse(self.path).path.startswith("/api/"):
            self.send_error(404)
            return
        self._handle_api(method)

    def _handle_api(self, method):
        parsed = urlparse(self.path)
        query  = parse_qs(parsed.query)

        payload = None
        length  = int(self.headers.get("Content-Length", 0) or 0)
        if length:
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                payload = None

        try:
            status, response_body = jobsuite_api.dispatch(method, parsed.path, query, payload, self.config)
        except Exception as e:
            print(f"[API] Unhandled error on {method} {parsed.path}: {e}")
            status, response_body = 500, {"error": str(e)}

        body = json.dumps(response_body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_server(root_dir: str, config: dict) -> str:
    SuiteHandler.root_dir = root_dir
    SuiteHandler.config   = config

    jobsuite_db.init_db()

    server = ThreadingHTTPServer(("127.0.0.1", 0), SuiteHandler)
    port   = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}/launcher.html"
    print(f"[INFO] JobSuite server running at http://127.0.0.1:{port}/")
    return url


# ---------------------------------------------------------------------------
# Path resolver
# ---------------------------------------------------------------------------

def resolve_root_dir() -> str:
    # PyInstaller frozen build: files live in sys._MEIPASS/src/
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidate = os.path.join(sys._MEIPASS, "src")
        launcher  = os.path.join(candidate, "launcher.html")
        if os.path.isfile(launcher):
            print(f"[INFO] Serving from bundle: {candidate}")
            return candidate

    # Development / script mode: directory containing this script
    candidate = os.path.dirname(os.path.abspath(__file__))
    launcher  = os.path.join(candidate, "launcher.html")
    if os.path.isfile(launcher):
        print(f"[INFO] Serving from: {candidate}")
        return candidate

    print(
        "\n[ERROR] Could not find launcher.html.\n"
        f"Searched: {candidate}\n"
        "Place launch_launcher.py in the JobSuite root folder.\n"
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch JobSuite as a desktop app."
    )
    parser.add_argument("--width",        "-W", type=int, default=1280)
    parser.add_argument("--height",       "-H", type=int, default=820)
    parser.add_argument("--no-resizable", action="store_true")
    parser.add_argument("--debug",        action="store_true",
        help="Enable browser DevTools")
    args = parser.parse_args()

    config   = load_config()
    root_dir = resolve_root_dir()

    url = start_server(root_dir, config)

    print(f"[INFO] Window: {args.width}x{args.height}")

    webview.create_window(
        title="JobSuite — Control Center",
        url=url,
        width=args.width,
        height=args.height,
        resizable=not args.no_resizable,
        min_size=(900, 650),
        js_api=LoggerAPI(config),
    )

    force_debug = os.environ.get("PYWEBVIEW_DEBUG", "").lower() in ("1", "true")
    webview.start(debug=args.debug or force_debug)


if __name__ == "__main__":
    main()
