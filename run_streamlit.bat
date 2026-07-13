@echo off
REM Launches the Streamlit UI locally, from this folder, so it shares the same
REM jobsuite.db / config.json as the desktop .exe (both resolve to this directory).
REM Running via Streamlit Community Cloud does NOT share this data — jobsuite.db
REM and config.json are gitignored, so a cloud deploy starts from an empty DB.
cd /d "%~dp0"
streamlit run streamlit_app.py
pause
