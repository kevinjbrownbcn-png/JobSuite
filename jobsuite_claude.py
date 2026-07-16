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


# ---------------------------------------------------------------------------
# JobPilot Mode B (Interview Assistant) — exact prompt text from
# _prompts/interview_session_starter_prompt.md and _prompts/interview_turn_prompt.md.
# ---------------------------------------------------------------------------

PERSONA_LABELS = {
    "recruiter": "Recruiter / HR",
    "hiring_manager": "Hiring Manager",
    "department_manager": "Department Manager",
    "peer": "Peer Interviewer",
}

INTERVIEW_STARTER_SYSTEM_PROMPT = """You are the Interview Session Manager.

Task:
Start a structured interview session for the selected persona.

Rules:
- Return JSON only.
- Use the candidate resume and job description as the basis.
- Set the tone and question style appropriate to the persona.
- Ask the first question only.
- Keep the first question grounded in the role and the candidate's background.

Output schema:
{
  "persona": "recruiter|hiring_manager|department_manager|peer",
  "goal": "string",
  "tone": "string",
  "firstQuestion": "string",
  "rubric": ["string"],
  "expectedSignals": ["string"]
}"""

INTERVIEW_TURN_SYSTEM_PROMPT = """You are the {persona} interviewer.

Task:
Evaluate the candidate's answer, then decide whether to ask a follow-up question or move on.

Rules:
- Return JSON only.
- Ask one question at a time.
- Base every question on the candidate CV, the job description, and prior answers.
- Do not repeat previously asked questions.
- Keep the tone realistic for the persona.
- Score the answer using the rubric.
- Score each rubric criterion on a scale of 1 (weak) to 5 (excellent). Never use any other range.
- If the answer is weak or incomplete, ask a focused follow-up.
- If the answer is sufficient, move to the next area.

Rubric:
- Relevance.
- Specificity.
- Role alignment.
- Communication clarity.
- Confidence and completeness.

Output schema:
{
  "persona": "recruiter|hiring_manager|department_manager|peer",
  "question": "string|null",
  "answerScore": 0,
  "criterionScores": {
    "relevance": 0,
    "specificity": 0,
    "roleAlignment": 0,
    "clarity": 0,
    "completeness": 0
  },
  "feedback": ["string"],
  "strengths": ["string"],
  "gaps": ["string"],
  "nextAction": "follow_up|next_persona|end_session",
  "followUpQuestion": "string|null"
}

Every value inside criterionScores must be an integer from 1 to 5."""


def _compute_answer_score(criterion_scores: dict) -> int:
    """Equal-weight average of the 5 rubric criteria (1-5 scale each per the master
    spec), normalized to 0-100 for consistency with the ATS scores. Claude's own
    `answerScore` field is discarded, same reasoning as _compute_overall_score above —
    a fixed formula is auditable and consistent run-to-run.

    Each raw value is clamped to [1, 5] before normalizing — the prompt instructs a
    1-5 scale, but an LLM can still ignore that (observed in testing: Claude returned
    7s and 8s once), and an out-of-range value must never push the final score past
    the 0-100 the rest of the app assumes."""
    values = [v for v in criterion_scores.values() if v is not None]
    if not values:
        return 0
    clamped = [max(1, min(5, v)) for v in values]
    normalized = [(v / 5) * 100 for v in clamped]
    return round(sum(normalized) / len(normalized))


def start_interview(persona: str, resume_structured: dict | None, job_structured: dict, api_key: str) -> dict:
    user_content = (
        f"Persona: {persona}\n\n"
        f"Structured resume:\n{json.dumps(resume_structured) if resume_structured else 'null (no resume data available — ask role/JD-focused questions only)'}\n\n"
        f"Structured job description:\n{json.dumps(job_structured)}"
    )
    return _call_claude(api_key, INTERVIEW_STARTER_SYSTEM_PROMPT, user_content)


def interview_turn(
    persona: str,
    resume_structured: dict | None,
    job_structured: dict,
    history: list,
    answer: str,
    api_key: str,
) -> dict:
    """`history` is a list of {"question": str, "answer": str|None} dicts for every
    prior turn in this session, oldest first. `answer` is the candidate's response to
    the most recent question in that history."""
    # .replace(), not .format() — the prompt's JSON schema block is full of literal
    # {braces} that .format() would try (and fail) to parse as format fields.
    system_prompt = INTERVIEW_TURN_SYSTEM_PROMPT.replace("{persona}", PERSONA_LABELS.get(persona, persona))
    history_text = "\n".join(
        f"Q{i + 1}: {h['question']}\nA{i + 1}: {h.get('answer') or '(no answer yet)'}"
        for i, h in enumerate(history)
    ) or "(none yet)"
    user_content = (
        f"Structured resume:\n{json.dumps(resume_structured) if resume_structured else 'null (no resume data available)'}\n\n"
        f"Structured job description:\n{json.dumps(job_structured)}\n\n"
        f"Conversation so far:\n{history_text}\n\n"
        f"Candidate's latest answer:\n{answer}"
    )
    result = _call_claude(api_key, system_prompt, user_content)
    result["answerScore"] = _compute_answer_score(result.get("criterionScores") or {})
    return result
