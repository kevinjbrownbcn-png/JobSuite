"""Server-side Claude analysis for JobPilot's ATS Analyzer (Mode A).

Deliberately a different model family from jobsuite_gemini.py's Gemini calls — the
whole point of a second ATS pass is an independent opinion, not the same model
re-scoring its own earlier match. Mirrors jobsuite_gemini.py's shape (a `_call_x`
core, plain functions returning parsed dicts) so the two modules stay easy to compare.
"""

import json
import re

import anthropic
import requests

from jobsuite_gemini import log_error

CLAUDE_MODEL = "claude-sonnet-5"

# Prompts below are the exact text from _prompts/ats_parser_prompt.md,
# _prompts/job_description_parser_prompt.md, and _prompts/ats_scorer_prompt.md.

ATS_PARSER_SYSTEM_PROMPT = """You are the ATS Resume Parser.

Task:
Extract only what is explicitly present in the resume.

Rules:
- Return JSON only.
- If a field is absent, use null or an empty array.
- Do not infer years of experience.
- Do not rewrite content.
- Do not add skills that are not explicitly stated.
- Do not hallucinate dates, employers, titles, or certifications.

Output schema:
{
  "name": "string|null",
  "contact": {
    "email": "string|null",
    "phone": "string|null",
    "location": "string|null",
    "links": ["string"]
  },
  "headline": "string|null",
  "skills": ["string"],
  "experience": [
    {
      "company": "string|null",
      "role": "string|null",
      "startDate": "string|null",
      "endDate": "string|null",
      "highlights": ["string"]
    }
  ],
  "education": ["string"],
  "certifications": ["string"],
  "languages": ["string"],
  "summary": "string|null"
}"""

JOB_PARSER_SYSTEM_PROMPT = """You are the Job Description Parser.

Task:
Extract the key hiring requirements from the job description.

Rules:
- Return JSON only.
- Do not infer details that are not stated.
- If a field is absent, use null or an empty array.
- Separate must-have and nice-to-have items.
- Keep the output concise and structured.

Output schema:
{
  "title": "string|null",
  "company": "string|null",
  "seniority": "string|null",
  "domain": "string|null",
  "mustHaveSkills": ["string"],
  "niceToHaveSkills": ["string"],
  "responsibilities": ["string"],
  "requirements": ["string"],
  "keywords": ["string"],
  "location": "string|null",
  "employmentType": "string|null"
}"""

ATS_SCORER_SYSTEM_PROMPT = """You are the ATS Scoring Engine.

Task:
Compare the structured resume and structured job description, then produce a fit analysis.

Rules:
- Return JSON only.
- Score from 0 to 100.
- Use evidence from the provided data only.
- Do not invent missing experience or skills.
- Explain every major score driver with short, specific notes.
- Be strict about missing evidence.
- Prefer actionable feedback over generic advice.

Scoring guidance:
- skillsMatch: 0-100
- seniorityMatch: 0-100
- domainMatch: 0-100
- experienceMatch: 0-100
- formatRisk: 0-100, where higher means more risk

Output schema:
{
  "overallScore": 0,
  "subscores": {
    "skillsMatch": 0,
    "seniorityMatch": 0,
    "domainMatch": 0,
    "experienceMatch": 0,
    "formatRisk": 0
  },
  "matchedSkills": ["string"],
  "missingSkills": ["string"],
  "missingEvidence": ["string"],
  "risks": ["string"],
  "recommendations": ["string"],
  "summary": "string"
}"""


def _extract_text_from_doc_elements(elements: list) -> str:
    """Walks a Google Docs API structural-elements array (paragraphs/textRuns, and
    table cells recursively) and concatenates the actual text content — this is the
    raw shape Make's "Get Content of a Document" module returns, not flattened text."""
    parts = []
    for el in elements:
        if "paragraph" in el:
            for pe in el["paragraph"].get("elements", []):
                if "textRun" in pe:
                    parts.append(pe["textRun"].get("content", ""))
        elif "table" in el:
            for row in el["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    parts.append(_extract_text_from_doc_elements(cell.get("content", [])))
    return "".join(parts)


def fetch_doc_text(doc_fetch_webhook_url: str, doc_id: str) -> str:
    """Fetches an arbitrary Drive doc's text by ID via a dedicated Make pipeline —
    unlike jobsuite_gemini.fetch_cv_text, which is hardcoded to one fixed file.

    The pipeline's "Get Content of a Document" module returns the raw Google Docs API
    structural-elements array (JSON), not flattened plain text, so this parses that
    out. Falls back to the raw response body if it isn't that JSON shape, so a future
    pipeline change to return plain text directly keeps working without a code change.
    """
    if not doc_fetch_webhook_url:
        raise ValueError("No doc_fetch_webhook configured in config.json.")
    resp = requests.post(doc_fetch_webhook_url, json={"doc_id": doc_id}, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Could not fetch doc {doc_id} via doc_fetch_webhook.")

    try:
        elements = json.loads(resp.text)
    except (json.JSONDecodeError, ValueError):
        return resp.text

    if not isinstance(elements, list):
        return resp.text

    return _extract_text_from_doc_elements(elements)


def _strip_json_fence(text: str) -> str:
    text = re.sub(r"^```json\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"```\s*$", "", text)
    return text.strip()


def _call_claude(api_key: str, system_prompt: str, user_content: str, max_tokens: int = 4096) -> dict:
    if not api_key:
        raise ValueError("Anthropic API key missing from config.json.")

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
    except anthropic.APIError as e:
        log_error("Claude_API_Rejection", str(e), str(e))
        raise RuntimeError(f"Claude API error: {e}") from e

    text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    if not text:
        log_error("Claude_Empty_Payload", "No_Text_Returned", str(response))
        raise RuntimeError("No text content returned from Claude.")

    cleaned = _strip_json_fence(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        log_error("Claude_Invalid_JSON", str(e), cleaned)
        raise RuntimeError(f"Claude returned invalid JSON: {e}") from e


def parse_resume(resume_text: str, api_key: str) -> dict:
    return _call_claude(api_key, ATS_PARSER_SYSTEM_PROMPT, f"Resume text:\n\n{resume_text}")


def parse_job_description(jd_text: str, api_key: str) -> dict:
    return _call_claude(api_key, JOB_PARSER_SYSTEM_PROMPT, f"Job description text:\n\n{jd_text}")


# Overall score weighting — matches _prompts/jobpilot_mvp_master_prompt.md's "MVP
# spec" ("Use a weighted score so the output is stable and explainable... 30% skills,
# 20% seniority, 20% domain match, 15% experience relevance, 15% formatting/clarity").
# formatRisk is inverted (100 - risk) before weighting since higher risk is worse,
# unlike the other four subscores where higher is better. Kept in sync with the
# weights described in js/jobpilot-ui.js and pages/3_JobPilot.py's UI copy.
OVERALL_SCORE_WEIGHTS = {
    "skillsMatch": 0.30,
    "seniorityMatch": 0.20,
    "domainMatch": 0.20,
    "experienceMatch": 0.15,
    "formatRisk": 0.15,
}


def _compute_overall_score(subscores: dict) -> int:
    weighted = 0.0
    for key, weight in OVERALL_SCORE_WEIGHTS.items():
        value = subscores.get(key) or 0
        weighted += weight * (100 - value if key == "formatRisk" else value)
    return round(weighted)


def score_ats_fit(resume_structured: dict, job_structured: dict, api_key: str) -> dict:
    user_content = (
        f"Structured resume:\n{json.dumps(resume_structured)}\n\n"
        f"Structured job description:\n{json.dumps(job_structured)}"
    )
    result = _call_claude(api_key, ATS_SCORER_SYSTEM_PROMPT, user_content)

    # Claude's own free-form overallScore is discarded in favor of this deterministic
    # calculation — same subscores either way, but a fixed formula is auditable and
    # consistent run-to-run, which an LLM's own holistic number isn't.
    result["overallScore"] = _compute_overall_score(result.get("subscores") or {})
    return result


def run_ats_analysis(resume_text: str, jd_text: str, api_key: str) -> dict:
    """Orchestrates the full ATS workflow: parse resume -> parse job -> score fit.
    Returns everything jobpilot_api.create_prep_session needs to store in one shot."""
    resume_structured = parse_resume(resume_text, api_key)
    job_structured = parse_job_description(jd_text, api_key)
    score = score_ats_fit(resume_structured, job_structured, api_key)
    return {
        "resume_structured": resume_structured,
        "job_structured": job_structured,
        "score": score,
    }
