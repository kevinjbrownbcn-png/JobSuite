"""Server-side Gemini analysis — ported from hunter-scanner.js, hunter-manual.js, and
launch_launcher.py's LoggerAPI.batch_scan_careers_hub (which was already server-side).

Moving these here means the API key never has to reach the browser, and both the
desktop app's local HTTP API and the Streamlit app can call the exact same functions
directly (no duplicated prompts/parsing logic between the two UIs).
"""

import datetime
import json
import os
import re
from urllib.parse import urldefrag, urljoin

import requests
from bs4 import BeautifulSoup

from jobsuite_config import exe_dir

GEMINI_MODEL_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

HUB_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
HUB_LINK_KEYWORDS = ("/apply/", "/job/", "/jobs/", "/careers/", "/position/", "/opening/", "/vacancy/")


def log_error(log_title: str, exception_msg: str, technical_payload: str) -> None:
    """Plain-function equivalent of LoggerAPI.write_error_log — usable without the
    pywebview bridge, so both the desktop server and Streamlit can call it directly."""
    try:
        logs_dir = os.path.join(exe_dir(), "logs")
        os.makedirs(logs_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_title = "".join(
            c for c in log_title if c.isalnum() or c in (" ", "_", "-")
        ).strip().replace(" ", "_")

        log_path = os.path.join(logs_dir, f"error_{timestamp}_{safe_title}.txt")
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
    except Exception as err:
        print(f"[ERROR] Failed to write error log: {err}")


def fetch_cv_text(gdrive_webhook_url: str) -> str:
    """Downloads the candidate's base CV text via the Make.com Drive-fetch webhook."""
    if not gdrive_webhook_url:
        raise ValueError("No gdrive_webhook configured in config.json.")
    resp = requests.post(gdrive_webhook_url, timeout=30)
    if not resp.ok:
        raise RuntimeError("Could not pull file text from Drive Webhook.")
    return resp.text


def _strip_json_fence(text: str) -> str:
    text = re.sub(r"^```json\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"```\s*$", "", text)
    return text.strip()


def _call_gemini(api_key: str, contents: list, use_search: bool = False, timeout: int = 60, log_on_error: bool = True) -> str:
    url = f"{GEMINI_MODEL_URL}?key={api_key}"
    body = {"contents": contents}
    if use_search:
        body["tools"] = [{"google_search": {}}]

    resp = requests.post(url, json=body, timeout=timeout)
    if not resp.ok:
        try:
            err_data = resp.json()
        except ValueError:
            err_data = {}
        message = (err_data.get("error") or {}).get("message") or f"Gemini gateway rejected request with status {resp.status_code}"
        if log_on_error:
            log_error("Gemini_API_Rejection", f"HTTP_Status_{resp.status_code}", json.dumps(err_data, indent=2))
        raise RuntimeError(message)

    data = resp.json()
    candidate = (data.get("candidates") or [None])[0]

    if candidate and candidate.get("finishReason") == "RECITATION":
        if log_on_error:
            log_error("Gemini_Empty_Payload", "RECITATION_FILTER_TRIPPED", json.dumps(data, indent=2))
        raise RuntimeError(
            "Safety blocker triggered (RECITATION). The model tried to output verbatim text. "
            "Try refining your niche keywords or searching for fewer positions at once."
        )

    text = None
    if candidate:
        parts = (candidate.get("content") or {}).get("parts") or []
        if parts:
            text = parts[0].get("text")

    if not text:
        if log_on_error:
            log_error("Gemini_Empty_Payload", "No_Text_Returned", json.dumps(data, indent=2))
        raise RuntimeError("No text content returned from the AI engine.")

    return _strip_json_fence(text)


def scan_web_for_jobs(roles: list, location: str, time_window: str, focus: str, api_key: str, gdrive_webhook_url: str) -> list:
    """Ports hunter-scanner.js's scanWebForJobs. Returns the raw list of discovered
    jobs — dedup filtering against localStorage stays a caller-side (JS) concern."""
    if not api_key:
        raise ValueError("Gemini API key missing from config.json.")

    base_cv_text = fetch_cv_text(gdrive_webhook_url)
    roles_str = ", ".join(roles)

    prompt = f"""Search the live web for real, active job postings matching these criteria:
Roles: {roles_str}
Locations: {location}
Recency: Published in {time_window}
Industry/Focus: {focus}

Evaluate every job you discover against this Candidate Base CV retrieved from Google Drive:
---
{base_cv_text}
---

CRITICAL SAFE-PARSING CONSTRAINTS (ANTI-RECITATION LAWS):
1. DO NOT copy or extract original job descriptions verbatim from the discovered search result snippets. Doing so trips the automated recitation safety filter.
2. You MUST clean, summarize, digest, and rephrase the core responsibilities and technical qualifications. Alter the exact lexical text signature of the original posting.
3. Keep the output content dense but fully unique—synthesize the required tracking frameworks, tools, platforms, and stack elements.

CRITICAL STRUCTURAL OUTPUT INSTRUCTIONS:
You MUST respond with a valid, raw JSON array of objects matching the schema below.
DO NOT write any markdown syntax wrapping, do not use backticks (```), and do not use any introductory or conversational text. If no jobs are discovered, return an empty array [] zero exceptions.

⚠️ CRITICAL URL CONSTRAINT:
The "link" parameter MUST be the actual, direct source webpage URL of the job posting (e.g., company greenhouse, lever, or linkedin address).
DO NOT use Google Search grounding metadata links or URLs containing "vertexaisearch.cloud.google.com/grounding-api-redirect". Extract the original deep link.

Schema Layout Expected:
[
  {{
    "job_title": "String",
    "company": "String",
    "location": "String",
    "link": "String - Deep link direct role webpage URL",
    "summary": "String - A highly concise 3-4 sentence high-level responsibility summary for the UI card",
    "description": "String - Summarized, synthesized, non-verbatim digest of the full qualifications, requirements, and tech stack elements.",
    "match_score": Number,
    "skills_gaps": ["String"],
    "resources": ["String"]
  }}
]"""

    raw_text = _call_gemini(api_key, [{"parts": [{"text": prompt}]}], use_search=True)

    if not raw_text.startswith("[") and not raw_text.startswith("{"):
        raise RuntimeError(raw_text)

    return json.loads(raw_text)


def analyze_manual_url(target_url: str, chosen_profile: str, api_key: str, gdrive_webhook_url: str) -> dict:
    """Ports hunter-manual.js's analyzeManualURL. Returns the single analyzed job dict —
    title/company/link overrides and Applied Through/Posting Source stamping stay a
    caller-side (JS) concern, same as before the move."""
    if not api_key:
        raise ValueError("Gemini API key missing from config.json.")

    base_cv_text = fetch_cv_text(gdrive_webhook_url)

    prompt = f"""You are a direct webpage parser. Visit this exact URL, bypass layout wrappers, and extract the full job description text:
Target URL: {target_url}

Once you have parsed the text from that webpage, execute a detailed skillset compatibility comparison against this Candidate Base CV:
---
{base_cv_text}
---

CRITICAL CORE FOCUS MODALITY:
The candidate is optimizing specifically for a "{chosen_profile}" track framework assignment. Measure compatibility, skills gaps, and resources matching that domain lens precisely.

CRITICAL STRUCTURAL OUTPUT INSTRUCTIONS:
You MUST respond with a valid, single-item raw JSON array containing exactly one object matching the schema below.
DO NOT write any markdown syntax wrapping, do not use backticks (```), and do not write any conversational context words.

Schema Layout Expected:
[
  {{
    "profile": "{chosen_profile}",
    "job_title": "String - Exact position name extracted from page",
    "company": "String - Hiring company name extracted from page",
    "location": "String - Location/remote policy info",
    "link": "{target_url}",
    "summary": "String - A highly concise 3-4 sentence high-level responsibility summary for the UI card",
    "description": "String - Provide the COMPLETE, RAW, UNABRIDGED job description text in full verbatim.",
    "match_score": Number,
    "skills_gaps": ["String - Missing terms/tools"],
    "resources": ["String - Preparation guides/courses"]
  }}
]"""

    raw_text = _call_gemini(api_key, [{"parts": [{"text": prompt}]}], use_search=True)
    single_job_array = json.loads(raw_text)
    return single_job_array[0]


def analyze_manual_text(pasted_description: str, chosen_profile: str, typed_title: str, typed_company: str, api_key: str, gdrive_webhook_url: str) -> dict:
    """Ports hunter-manual.js's analyzeManualText. Returns the single analyzed job dict."""
    if not api_key:
        raise ValueError("Gemini API key missing from config.json.")

    base_cv_text = fetch_cv_text(gdrive_webhook_url)

    title_hint = typed_title if typed_title else (
        "NOT PROVIDED. You must analyze the text block and determine the exact job title. "
        'If impossible to determine, return an empty string "" explicitly.'
    )
    company_hint = typed_company if typed_company else (
        "NOT PROVIDED. You must analyze the text block and determine the hiring company or studio name. "
        'If impossible to determine, return an empty string "" explicitly.'
    )

    technical_instruction_text = f"""You are an internal skillset compliance engine. Analyze the appended Job Description text block against the provided Candidate Base CV text block.

CRITICAL CORE FOCUS MODALITY:
The candidate is optimizing specifically for a "{chosen_profile}" track framework assignment. Measure compliance, matching keywords, missing tools, and gap ratios focused purely on this domain lens.

METADATA INFERENCE INSTRUCTIONS:
- Position Title Provided: {title_hint}
- Company Provided: {company_hint}

CRITICAL STRUCTURAL OUTPUT INSTRUCTIONS:
You MUST respond with a valid, single-item raw JSON array containing exactly one object matching the schema layout below.
DO NOT use markdown code wraps like ```json, write no preambles, and return nothing but the raw structural array text.

Schema Layout Expected:
[
  {{
    "profile": "{chosen_profile}",
    "job_title": "String - Use the provided title, or your inferred title. If completely unknown, return an empty string \\"\\" explicitly.",
    "company": "String - Use the provided company, or your inferred company. If completely unknown, return an empty string \\"\\" explicitly.",
    "location": "Manual Text Audit",
    "link": "Manual Upload",
    "summary": "String - A highly concise 3-4 sentence high-level responsibility summary for the UI card",
    "description": "PLACEHOLDER",
    "match_score": Number,
    "skills_gaps": ["String - Missing tools/methodologies"],
    "resources": ["String - Preparation paths"]
  }}
]"""

    contents = [{
        "parts": [
            {"text": technical_instruction_text},
            {"text": f"CANDIDATE BASE CV PROFILE:\n{base_cv_text}"},
            {"text": f"TARGET JOB DESCRIPTION TO ANALYZE:\n{pasted_description}"},
        ]
    }]

    raw_text = _call_gemini(api_key, contents, use_search=False)

    if not raw_text.startswith("[") and not raw_text.startswith("{"):
        raise RuntimeError("Invalid response format generated by the AI parser.")

    single_job_array = json.loads(raw_text)
    return single_job_array[0]


def analyze_careers_hub(hub_url: str, profile_context: str, api_key: str) -> list:
    """Ports launch_launcher.py's former LoggerAPI.batch_scan_careers_hub — crawls a
    corporate careers hub page, finds individual job links, and scores each one."""
    if not api_key:
        raise ValueError("No Gemini API key found in config.json.")

    print(f"[HUB] Crawling hub index: {hub_url}")
    try:
        hub_resp = requests.get(hub_url, headers=HUB_HEADERS, timeout=15)
        hub_resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Could not fetch hub page: {e}")

    soup = BeautifulSoup(hub_resp.text, "html.parser")

    job_links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        absolute = urljoin(hub_url, href)
        absolute, _ = urldefrag(absolute)
        if any(kw in absolute.lower() for kw in HUB_LINK_KEYWORDS) and absolute != hub_url:
            job_links.add(absolute)

    print(f"[HUB] Found {len(job_links)} candidate job link(s)")
    if not job_links:
        raise RuntimeError(
            "No individual job posting links found on the hub page. "
            "The site structure may use JavaScript rendering which requires a different approach."
        )

    jobs = []
    for link in list(job_links)[:20]:
        print(f"[HUB] Analysing: {link}")
        try:
            job_resp = requests.get(link, headers=HUB_HEADERS, timeout=15)
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
            raw_text = _call_gemini(api_key, [{"parts": [{"text": prompt}]}], use_search=False, timeout=30, log_on_error=False)
            job_data = json.loads(raw_text)
            jobs.append(job_data)
            print(f"[HUB] Match score {job_data.get('match_score', '?')} — {job_data.get('job_title', '?')}")
        except Exception as e:
            print(f"[HUB] Gemini analysis failed for {link}: {e}")
            continue

    if not jobs:
        raise RuntimeError("Could not analyse any job postings from the hub. Check the terminal for details.")

    print(f"[HUB] Scan complete — {len(jobs)} job(s) analysed.")
    return jobs
