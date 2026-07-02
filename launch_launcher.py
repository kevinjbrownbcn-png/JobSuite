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
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, urljoin, urldefrag


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
# Config loader
# ---------------------------------------------------------------------------

CONFIG_KEYS = ("gemini_api_key", "gdrive_webhook", "export_webhook")


def exe_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def load_config() -> dict:
    config_path = os.path.join(exe_dir(), "config.json")
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

    def batch_scan_careers_hub(self, hub_url: str, profile_context: str) -> str:
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError as e:
            return json.dumps({"status": "error", "message": f"Missing dependency: {e}. Run: pip install requests beautifulsoup4"})

        api_key = self._config.get("gemini_api_key", "")
        if not api_key:
            return json.dumps({"status": "error", "message": "No Gemini API key found in config.json."})

        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        headers    = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        print(f"[HUB] Crawling hub index: {hub_url}")
        try:
            hub_resp = requests.get(hub_url, headers=headers, timeout=15)
            hub_resp.raise_for_status()
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Could not fetch hub page: {e}"})

        soup     = BeautifulSoup(hub_resp.text, "html.parser")
        base_url = hub_url

        job_links = set()
        keywords  = ("/apply/", "/job/", "/jobs/", "/careers/", "/position/", "/opening/", "/vacancy/")

        for a in soup.find_all("a", href=True):
            href     = a["href"].strip()
            absolute = urljoin(base_url, href)
            absolute, _ = urldefrag(absolute)
            if any(kw in absolute.lower() for kw in keywords):
                if absolute != hub_url:
                    job_links.add(absolute)

        print(f"[HUB] Found {len(job_links)} candidate job link(s)")

        if not job_links:
            return json.dumps({"status": "error", "message": "No individual job posting links found on the hub page. The site structure may use JavaScript rendering which requires a different approach."})

        jobs = []
        for link in list(job_links)[:20]:
            print(f"[HUB] Analysing: {link}")
            try:
                job_resp = requests.get(link, headers=headers, timeout=15)
                job_resp.raise_for_status()
                job_soup = BeautifulSoup(job_resp.text, "html.parser")
                for tag in job_soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                job_text = job_soup.get_text(separator="\n", strip=True)[:6000]
            except Exception as e:
                print(f"[HUB] Skipping {link} — fetch failed: {e}")
                continue

            prompt = f"""You are a job match analyser. Evaluate this job posting for a candidate with a {profile_context} background.

Job posting URL: {link}
Job posting content:
{job_text}

Respond ONLY with a valid JSON object (no markdown, no code fences) in exactly this structure:
{{
  "job_title": "...",
  "company": "...",
  "location": "...",
  "match_score": <integer 0-100>,
  "summary": "...",
  "skills_gaps": ["...", "..."],
  "link": "{link}"
}}"""

            try:
                gemini_resp = requests.post(
                    gemini_url,
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                    timeout=30
                )
                gemini_resp.raise_for_status()
                raw_text = gemini_resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                raw_text = raw_text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
                job_data = json.loads(raw_text)
                jobs.append(job_data)
                print(f"[HUB] Match score {job_data.get('match_score', '?')} — {job_data.get('job_title', '?')}")
            except Exception as e:
                print(f"[HUB] Gemini analysis failed for {link}: {e}")
                continue

        if not jobs:
            return json.dumps({"status": "error", "message": "Could not analyse any job postings from the hub. Check the terminal for details."})

        print(f"[HUB] Scan complete — {len(jobs)} job(s) analysed.")
        return json.dumps({"status": "success", "jobs": jobs})


# ---------------------------------------------------------------------------
# Config script builder — injects API key / webhook values into HTML pages
# ---------------------------------------------------------------------------

def build_config_script(config: dict) -> str:
    if not config:
        return ""

    lines = ["(function () {"]

    for cfg_key, ls_key in [("gdrive_webhook", "gdrive_webhook"),
                             ("export_webhook",  "export_webhook")]:
        if cfg_key in config:
            lines.append(
                f"  localStorage.setItem({json.dumps(ls_key)}, {json.dumps(config[cfg_key])});"
            )

    if "gemini_api_key" in config:
        key  = json.dumps(config["gemini_api_key"])
        base = json.dumps("https://generativelanguage.googleapis.com")
        lines += [
            f"  var _k = {key}, _b = {base}, _f = window.fetch.bind(window);",
            "  window.fetch = function (url, opts) {",
            "    if (typeof url === 'string' && url.indexOf(_b) === 0) {",
            "      url = url.indexOf('key=') !== -1",
            "        ? url.replace(/([?&]key=)[^&]*/, '$1' + _k)",
            "        : url + (url.indexOf('?') === -1 ? '?' : '&') + 'key=' + _k;",
            "    }",
            "    return _f(url, opts);",
            "  };",
        ]

    lines += [
        "  console.log('[config] JobSuite config script executed.');",
        "  console.log('[config] fetch wrapper installed:', window.fetch.toString().indexOf('_k') !== -1);",
    ]
    lines.append("}());")
    return "\n".join(lines)


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
    """Serves all files in the JobSuite root.
    Config script is injected into every HTML page served."""

    root_dir  = ""
    config_js = ""

    def log_message(self, fmt, *args):
        print(f"[SERVER] {self.address_string()} - {fmt % args}")

    def do_GET(self):
        path = urlparse(self.path).path

        # Default to launcher.html for root requests
        if path in ("/", ""):
            path = "/launcher.html"

        file_path = os.path.normpath(os.path.join(self.root_dir, path.lstrip("/")))

        # Safety: prevent directory traversal outside root
        if not file_path.startswith(self.root_dir):
            self.send_error(403)
            return

        if not os.path.isfile(file_path):
            print(f"[SERVER] 404 not found: {file_path}")
            self.send_error(404)
            return

        ext  = os.path.splitext(file_path)[1].lower()
        mime = MIME_TYPES.get(ext, "application/octet-stream")

        if ext == ".html" and self.config_js:
            with open(file_path, "r", encoding="utf-8") as fh:
                html = fh.read()
            tag = f"<script>\n{self.config_js}\n</script>"
            idx = html.lower().find("<body")
            if idx != -1:
                close = html.find(">", idx) + 1
                html  = html[:close] + "\n" + tag + "\n" + html[close:]
            body = html.encode("utf-8")
        else:
            with open(file_path, "rb") as fh:
                body = fh.read()

        self.send_response(200)
        self.send_header("Content-Type",   mime)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_server(root_dir: str, config_js: str) -> str:
    SuiteHandler.root_dir  = root_dir
    SuiteHandler.config_js = config_js

    server = HTTPServer(("127.0.0.1", 0), SuiteHandler)
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

    config_js = build_config_script(config)
    url       = start_server(root_dir, config_js)

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
