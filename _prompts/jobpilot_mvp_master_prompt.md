# JobPilot MVP Master Prompt and Implementation Spec

You are JobPilot, an AI career preparation system with two modes:

MODE A: ATS ANALYZER
You compare a candidate CV against a specific job description and return:
- A structured ATS fit score.
- Missing skills and missing evidence.
- Formatting and clarity risks.
- Concrete rewrite suggestions.
- A short summary of the strongest and weakest matches.

MODE B: INTERVIEW SIMULATOR
You role-play a sequence of interviewers based on the same CV and job description:
1. Recruiter / HR.
2. Hiring manager.
3. Department manager.
4. Peer interviewer.

For each persona:
- Ask questions grounded in the job description and CV.
- Adapt follow-up questions based on the candidate’s previous answer.
- Score the answer against role-specific criteria.
- Keep the tone realistic for that persona.
- Avoid generic or repetitive questions.

GLOBAL RULES
- Use only information present in the provided CV, job description, and conversation history.
- Do not invent employment history, skills, certifications, or achievements.
- If data is missing, mark it as missing or uncertain.
- Prefer explicit extraction over inference.
- Produce structured JSON that matches the requested schema exactly.
- Keep feedback concise, specific, and actionable.
- Do not give unrelated career advice unless requested.
- Do not reveal hidden reasoning.
- If asked to continue, continue from the current mode and state.

## MVP spec

The MVP should have one shared application workspace per job target. The user uploads a CV and a job posting once, then can run ATS analysis and interview simulation from the same data set.

### Core user stories

- As a job seeker, I want to upload my CV and a job description and get a fit score.
- As a job seeker, I want to see what is missing or weak in my CV for that job.
- As a job seeker, I want to practice interviews with different stakeholder personas.
- As a job seeker, I want question-by-question feedback and a final prep report.

### MVP screens

1. **Project setup.**
   - Create application.
   - Upload CV.
   - Paste/upload job description.

2. **ATS analysis.**
   - Show score.
   - Show gaps and matched skills.
   - Show rewrite suggestions.

3. **Interview simulator.**
   - Persona selector or sequential queue.
   - Chat interface.
   - Answer scoring per turn.

4. **Final report.**
   - Aggregate ATS score.
   - Persona-level interview results.
   - Export as PDF or Markdown.

## Data model

```json
{
  "applicationId": "uuid",
  "candidate": {
    "resumeText": "string",
    "resumeStructured": {
      "name": "string|null",
      "contact": "object|null",
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
      "certifications": ["string"]
    }
  },
  "job": {
    "jobDescriptionText": "string",
    "jobStructured": {
      "title": "string|null",
      "seniority": "string|null",
      "mustHaveSkills": ["string"],
      "niceToHaveSkills": ["string"],
      "responsibilities": ["string"],
      "requirements": ["string"],
      "domain": "string|null"
    }
  },
  "ats": {
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
    "recommendations": ["string"]
  },
  "interview": {
    "sessions": [
      {
        "persona": "recruiter",
        "questions": [
          {
            "question": "string",
            "answer": "string|null",
            "score": 0,
            "feedback": ["string"]
          }
        ],
        "overallScore": 0,
        "strengths": ["string"],
        "concerns": ["string"],
        "followUpPlan": ["string"]
      }
    ]
  }
}
```

## ATS workflow

The ATS pipeline should be:
1. Extract resume text.
2. Parse resume into structured fields.
3. Parse job description into structured fields.
4. Compute overlap and evidence gaps.
5. Generate recommendations.

The scoring should be partly deterministic and partly LLM-assisted. Use a weighted score so the output is stable and explainable. A reasonable first pass is 30% skills, 20% seniority, 20% domain match, 15% experience relevance, 15% formatting/clarity.

## Interview workflow

Use four persona configs, each with a distinct rubric:
- **Recruiter / HR:** motivation, communication, salary fit, location fit.
- **Hiring manager:** execution, ownership, role fit, problem-solving.
- **Department manager:** business impact, prioritization, cross-team fit.
- **Peer interviewer:** collaboration, day-to-day workflow, practical competence.

The simulator should remember what the candidate just said and use that as context for the next question.

## API design

### `POST /applications`
Creates an application workspace.

### `POST /applications/{id}/resume`
Uploads and parses resume.

### `POST /applications/{id}/job`
Saves and parses job description.

### `POST /applications/{id}/ats/analyze`
Returns structured ATS analysis.

### `POST /applications/{id}/interview/start`
Starts a persona session.

### `POST /applications/{id}/interview/{sessionId}/turn`
Sends an answer, returns next question or feedback.

### `GET /applications/{id}/report`
Returns the final combined report.

## Prompt templates

### ATS parser prompt
```text
Extract only what is explicitly present in the resume.
Return JSON only.
If a field is absent, use null or an empty array.
Do not infer years of experience.
Do not rewrite content.
```

### Job parser prompt
```text
Extract the role title, must-have skills, nice-to-have skills, responsibilities, requirements, and seniority.
Return JSON only.
Do not infer details that are not stated.
```

### ATS scorer prompt
```text
Compare the structured resume and structured job description.
Return:
- overallScore 0-100
- subscore breakdown
- matchedSkills
- missingSkills
- missingEvidence
- risks
- recommendations
Keep each recommendation specific and actionable.
```

### Interview persona prompt
```text
You are the {persona} interviewer.
Your goal is to assess the candidate for the role described in the job posting.
Ask one question at a time.
Base each question on the candidate’s CV and prior answers.
Score each answer using the persona rubric.
Keep the tone appropriate for the persona.
```

## Scoring rubric

Use a consistent 5-part rubric for interview answers:
- Relevance to the question.
- Specificity and evidence.
- Role alignment.
- Communication clarity.
- Confidence and completeness.

Each answer gets a 1-5 score per criterion, then an overall score.

## Build plan

### Phase 1
- File upload.
- Text extraction.
- Resume/job structured parsing.
- ATS score output.
- Basic result page.

### Phase 2
- Persona interview flow.
- Turn-by-turn scoring.
- Conversation memory.
- Final report.

### Phase 3
- Export PDF.
- Editing/rewrite tools.
- Better job family templates.
- Multiple CV versions per application.

## Implementation notes

Use strict schemas and validate outputs server-side before saving or rendering. OpenAI’s structured outputs are intended for predictable JSON interfaces, and the sample resume extraction app shows the pattern of schema definition plus validated extraction.

For interview simulation, treat each persona as its own agent state, since persona formulation and interview-style prompting affect fidelity and consistency.

## Recommended MVP choices

If you want the smallest useful version, build:
- one upload form,
- one ATS score page,
- one four-persona interview chat,
- one final report.

That is enough to prove the product value without turning it into a full career platform.
