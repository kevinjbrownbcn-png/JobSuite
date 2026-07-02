import { fetchBaseCVText } from './hunter-config.js';
import { renderJobCards, updateSelectedCounter } from './hunter-ui.js';

export async function scanWebForJobs() {
    const hookUrl = localStorage.getItem('gdrive_webhook');
    if (!hookUrl) {
        window.showAlert('Setup Missing', 'Please verify your Make fetch connection hook settings inside Tab 3.', 'error');
        return;
    }

    const checkedRoles = Array.from(document.querySelectorAll('#roles-checkbox-list input[type="checkbox"]:checked')).map(cb => cb.value);
    if (checkedRoles.length === 0) {
        window.showAlert('Error', 'Select at least one position type checkbox.', 'error');
        return;
    }

    const loadingState = document.getElementById('loading-state');
    const resultsContainer = document.getElementById('results-container');
    const bulkPanel = document.getElementById('bulk-controls-panel');

    document.getElementById('empty-state').classList.add('hidden');
    resultsContainer.classList.add('hidden');
    bulkPanel.classList.add('hidden');

    let baseCVText = "";
    try {
        baseCVText = await fetchBaseCVText(hookUrl, loadingState);
    } catch (err) {
        loadingState.classList.add('hidden');
        document.getElementById('empty-state').classList.remove('hidden');
        window.showAlert('Drive Sync Failed', err.message, 'error');
        return;
    }

    document.getElementById('loader-title').textContent = "Harvesting Open Web Postings...";
    document.getElementById('loader-desc').textContent = "Analyzing job markets, ranking criteria matches, and checking framework skill gaps.";

    const location = document.getElementById('search-location').value;
    const timeWindow = document.getElementById('search-time').value;
    const focusKeywords = document.getElementById('search-focus').value;

    const searchPrompt = `Search the live web for real, active job postings matching these criteria:
Roles: ${checkedRoles.join(', ')}
Locations: ${location}
Recency: Published in ${timeWindow}
Industry/Focus: ${focusKeywords}

Evaluate every job you discover against this Candidate Base CV retrieved from Google Drive:
---
${baseCVText}
---

CRITICAL SAFE-PARSING CONSTRAINTS (ANTI-RECITATION LAWS):
1. DO NOT copy or extract original job descriptions verbatim from the discovered search result snippets. Doing so trips the automated recitation safety filter.
2. You MUST clean, summarize, digest, and rephrase the core responsibilities and technical qualifications. Alter the exact lexical text signature of the original posting.
3. Keep the output content dense but fully unique—synthesize the required tracking frameworks, tools, platforms, and stack elements.

CRITICAL STRUCTURAL OUTPUT INSTRUCTIONS:
You MUST respond with a valid, raw JSON array of objects matching the schema below.
DO NOT write any markdown syntax wrapping, do not use backticks (\`\`\`), and do not use any introductory or conversational text. If no jobs are discovered, return an empty array [] zero exceptions.

⚠️ CRITICAL URL CONSTRAINT:
The "link" parameter MUST be the actual, direct source webpage URL of the job posting (e.g., company greenhouse, lever, or linkedin address).
DO NOT use Google Search grounding metadata links or URLs containing "vertexaisearch.cloud.google.com/grounding-api-redirect". Extract the original deep link.

Schema Layout Expected:
[
  {
    "job_title": "String",
    "company": "String",
    "location": "String",
    "link": "String - Deep link direct role webpage URL",
    "summary": "String - A highly concise 3-4 sentence high-level responsibility summary for the UI card",
    "description": "String - Summarized, synthesized, non-verbatim digest of the full qualifications, requirements, and tech stack elements.",
    "match_score": Number,
    "skills_gaps": ["String"],
    "resources": ["String"]
  }
]`;

    let rawJSONText = "";
    try {
        const targetUrl = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent`;

        const apiResponse = await window.fetch(targetUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{ parts: [{ text: searchPrompt }] }],
                tools: [{ google_search: {} }]
            })
        });

        if (!apiResponse.ok) {
            const errData = await apiResponse.json();
            if (window.pywebview && window.pywebview.api) {
                await window.pywebview.api.write_error_log("Scanner_API_Rejection", `HTTP_Status_${apiResponse.status}`, JSON.stringify(errData, null, 2));
            }
            throw new Error(errData.error?.message || `Gemini gateway rejected search request with status code ${apiResponse.status}`);
        }

        const resData = await apiResponse.json();

        const candidate = resData.candidates?.[0];
        if (candidate && candidate.finishReason === "RECITATION") {
            if (window.pywebview && window.pywebview.api) {
                await window.pywebview.api.write_error_log("Scanner_Empty_Payload", "RECITATION_FILTER_TRIPPED", JSON.stringify(resData, null, 2));
            }
            throw new Error("Safety blocker triggered (RECITATION). The model tried to output verbatim text. Try refining your niche keywords or searching for fewer positions at once.");
        }

        rawJSONText = candidate?.content?.parts?.[0]?.text;

        if (!rawJSONText) {
            if (window.pywebview && window.pywebview.api) {
                await window.pywebview.api.write_error_log("Scanner_Empty_Payload", "No_Text_Returned", JSON.stringify(resData, null, 2));
            }
            throw new Error("No text content returned from the AI search engine.");
        }

        rawJSONText = rawJSONText.replace(/^```json\s*/i, '').replace(/```\s*$/, '').trim();

        if (!rawJSONText.startsWith('[') && !rawJSONText.startsWith('{')) {
            throw new Error(rawJSONText);
        }
        const jobs = JSON.parse(rawJSONText);

        const dedupRegistry = JSON.parse(localStorage.getItem('hunter_dedup_registry')) || {};
        const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;
        const currentTime = new Date().getTime();

        const uniqueFreshJobs = jobs.filter(job => {
            if (!job.job_title || !job.company) return true;
            const signatureKey = `${job.job_title.toLowerCase().trim()}_${job.company.toLowerCase().trim()}`;

            if (dedupRegistry[signatureKey]) {
                const structuralAge = currentTime - dedupRegistry[signatureKey];
                if (structuralAge < SEVEN_DAYS_MS) {
                    console.log(`Deduplication Filter: Dropped tracked row "${job.job_title}" at ${job.company}.`);
                    return false;
                }
            }
            return true;
        });

        renderJobCards(uniqueFreshJobs);
        loadingState.classList.add('hidden');
        resultsContainer.classList.remove('hidden');

        if (uniqueFreshJobs.length > 0) {
            bulkPanel.classList.remove('hidden');
            updateSelectedCounter();
            window.showAlert('Scan Completed', `Successfully found and analyzed ${uniqueFreshJobs.length} new roles!`, 'success');
        } else {
            document.getElementById('empty-state').classList.remove('hidden');
            window.showAlert('Scan Completed', 'Discovered roles match recent exports and were filtered.', 'info');
        }

    } catch (error) {
        loadingState.classList.add('hidden');
        document.getElementById('empty-state').classList.remove('hidden');

        if (window.pywebview && window.pywebview.api) {
            const debugPayload = {
                errorMessage: error.message,
                recoveredRawText: rawJSONText,
                targetParams: { location, timeWindow, focusKeywords, checkedRoles }
            };
            await window.pywebview.api.write_error_log("Scanner_Execution_Fault", error.name || "Exception", JSON.stringify(debugPayload, null, 2));
        }

        window.showAlert('Web Scraper Engine Interrupted', `${error.message}. A technical trace log check has been saved to /logs.`, 'error');
    }
}

window.scanWebForJobs = scanWebForJobs;
