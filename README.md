# JobSuite

A local-first job-hunting suite: find postings, score them against your CV, generate
tailored application materials, track the pipeline, and run a second AI opinion on
each application's actual fit — all backed by one shared SQLite database
(`jobsuite.db`), available as both a desktop app and a Streamlit app.

## Modules

### 🔎 AI Job Hunter (`hunter.html`)
Scans the live web for postings, or audits a pasted job description/URL/careers-hub
page by hand, scoring each against your base CV via Gemini. Discovered postings get
staged in **Staged Matches**, where you can send one to prep (generates a tailored
CV/cover letter via a Make.com pipeline), mark it applied, or discard it.

### 📊 Pipeline Analytics (`dashboard.html`)
KPI dashboard and full applications table for everything that's actually been applied
to — response rate, interview rate, offer rate, stale trackings, and more, plus an
editable, filterable, sortable view of every application.

### 🧭 JobPilot (`jobpilot.html`)
Runs a second, independent AI pass — Claude, not Gemini — scoring the *tailored* CV
Pipeline 01 generated for a specific application against that application's actual job
description. Produces a weighted fit score (Skills/Seniority/Domain/Experience/Format
Risk), matched/missing skills, and concrete recommendations.

### 🎤 Interview Assistant (`interview.html`)
Mock-interview practice against four stakeholder personas (Recruiter/HR, Hiring
Manager, Department Manager, Peer), each asking grounded, CV/JD-aware questions and
scoring your answers turn by turn on a fixed rubric (relevance, specificity, role
alignment, clarity, completeness). Reuses JobPilot's parsed CV/JD data when it
exists; otherwise parses the job description (and tailored CV, if any) on the spot,
so postings that predate a JobPilot run are still practiceable. Personas run
independently and are re-runnable.

## Running it

**Desktop**: run the built `.exe` in `dist/` (build with `build_exe.py`).

**Streamlit**: double-click `run_streamlit.bat`, or run `streamlit run streamlit_app.py`
from this folder directly. It must run from this same folder (not a different clone)
to share the same `jobsuite.db`/`config.json` the desktop app uses — see
`jobsuite_config.py`'s `data_dir()` for how that's resolved.

Both share the exact same database and config file — there is no sync step, they're
just the same files.

## Configuration

Copy your real values into `config.json` (never committed — see `.gitignore`):

- `gemini_api_key` — Hunter's match scoring/scanning
- `anthropic_api_key` — JobPilot's ATS analysis and Interview Assistant's persona chats
- `gdrive_webhook`, `docgen_webhook`, `drive_cleanup_webhook`, `doc_fetch_webhook`,
  `export_webhook` — Make.com pipeline URLs (see `jobsuite_webhooks.py` and
  `jobsuite_claude.py` for what each one does)

The Make.com scenarios themselves aren't part of this repo.

## Theming

Dark/light toggle in every page's header, persisted in `localStorage` (desktop) or
`st.session_state` (Streamlit) — see `js/theme.js` and `streamlit_common.apply_theme()`.
