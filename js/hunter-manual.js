import { fetchBaseCVText, getApiKeyFromConfig } from './hunter-config.js';

export async function analyzeManualURL() {
    const activeKey = await getApiKeyFromConfig();
    const hookUrl = localStorage.getItem('gdrive_webhook');

    const urlInputElement = document.getElementById('direct-analysis-url');
    const profileSelector = document.getElementById('direct-analysis-profile');
    if (!urlInputElement || !profileSelector) return;

    const targetURL = urlInputElement.value.trim();
    const chosenProfile = profileSelector.value;

    if (!activeKey) {
        window.showAlert('Configuration Error', 'Gemini API key missing inside config.json or storage parameters.', 'error');
        return;
    }
    if (!hookUrl) {
        window.showAlert('Setup Missing', 'Please verify your Make fetch connection hook settings inside Tab 4.', 'error');
        return;
    }
    if (!targetURL) {
        window.showAlert('Input Required', 'Please paste a valid job posting link inside the Direct URL analyzer.', 'error');
        return;
    }

    const loadingState = document.getElementById('loading-state');
    const resultsContainer = document.getElementById('results-container');
    const bulkPanel = document.getElementById('bulk-controls-panel');

    document.getElementById('empty-state').classList.add('hidden');
    if (resultsContainer) resultsContainer.classList.add('hidden');
    if (bulkPanel) bulkPanel.classList.add('hidden');

    let baseCVText = "";
    try {
        baseCVText = await fetchBaseCVText(hookUrl, loadingState);
    } catch (err) {
        if (loadingState) loadingState.classList.add('hidden');
        document.getElementById('empty-state').classList.remove('hidden');
        window.showAlert('Drive Sync Failed', err.message, 'error');
        return;
    }

    document.getElementById('loader-title').textContent = "Reading Target Webpage...";
    document.getElementById('loader-desc').textContent = `Extracting job specifications tailored to profile context framework: ${chosenProfile}.`;

    const manualAnalysisPrompt = `You are a direct webpage parser. Visit this exact URL, bypass layout wrappers, and extract the full job description text:
Target URL: ${targetURL}

Once you have parsed the text from that webpage, execute a detailed skillset compatibility comparison against this Candidate Base CV:
---
${baseCVText}
---

CRITICAL CORE FOCUS MODALITY:
The candidate is optimizing specifically for a "${chosenProfile}" track framework assignment. Measure compatibility, skills gaps, and resources matching that domain lens precisely.

CRITICAL STRUCTURAL OUTPUT INSTRUCTIONS:
You MUST respond with a valid, single-item raw JSON array containing exactly one object matching the schema below.
DO NOT write any markdown syntax wrapping, do not use backticks (\`\`\`), and do not write any conversational context words.

Schema Layout Expected:
[
  {
    "profile": "${chosenProfile}",
    "job_title": "String - Exact position name extracted from page",
    "company": "String - Hiring company name extracted from page",
    "location": "String - Location/remote policy info",
    "link": "${targetURL}",
    "summary": "String - A highly concise 3-4 sentence high-level responsibility summary for the UI card",
    "description": "String - Provide the COMPLETE, RAW, UNABRIDGED job description text in full verbatim.",
    "match_score": Number,
    "skills_gaps": ["String - Missing terms/tools"],
    "resources": ["String - Preparation guides/courses"]
  }
]`;

    let rawJSONText = "";
    try {
        const targetUrl = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${activeKey}`;

        const apiResponse = await window.fetch(targetUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{ parts: [{ text: manualAnalysisPrompt }] }],
                tools: [{ google_search: {} }]
            })
        });

        if (!apiResponse.ok) {
            const errData = await apiResponse.json();
            throw new Error(errData.error?.message || `Gateway rejected payload layout execution.`);
        }

        const resData = await apiResponse.json();
        rawJSONText = resData.candidates?.[0]?.content?.parts?.[0]?.text;

        if (!rawJSONText) throw new Error("No usable metrics string returned from search engine matrix layers.");

        rawJSONText = rawJSONText.replace(/^```json\s*/i, '').replace(/```\s*$/, '').trim();

        const singleJobArray = JSON.parse(rawJSONText);
        singleJobArray[0].profile = chosenProfile;

        window.renderJobCards(singleJobArray);
        urlInputElement.value = '';

        if (loadingState) loadingState.classList.add('hidden');
        if (resultsContainer) resultsContainer.classList.remove('hidden');
        if (bulkPanel) bulkPanel.classList.remove('hidden');
        window.updateSelectedCounter();

        window.showAlert('Analysis Complete', `Mapped skillset gaps under track: ${chosenProfile}!`, 'success');
    } catch (error) {
        if (loadingState) loadingState.classList.add('hidden');
        document.getElementById('empty-state').classList.remove('hidden');
        window.showAlert('Webpage Analysis Error', `${error.message}`, 'error');
    }
}

export async function analyzeManualText() {
    const activeKey = await getApiKeyFromConfig();
    const hookUrl = localStorage.getItem('gdrive_webhook');

    const titleEl = document.getElementById('manual-text-title');
    const companyEl = document.getElementById('manual-text-company');
    const urlEl = document.getElementById('manual-text-url');
    const descEl = document.getElementById('manual-description');
    const profileSelector = document.getElementById('manual-profile');

    if (!titleEl || !companyEl || !descEl || !profileSelector) {
        window.showAlert('Application Fault', 'UI form nodes are misaligned. Please re-verify hunter.html contents.', 'error');
        return;
    }

    const typedTitle = titleEl.value.trim();
    const typedCompany = companyEl.value.trim();
    const typedUrl = urlEl ? urlEl.value.trim() : '';
    const pastedDescription = descEl.value.trim();
    const chosenProfile = profileSelector.value;

    if (!activeKey) {
        window.showAlert('Configuration Error', 'Gemini API key could not be recovered from config.json or storage profiles.', 'error');
        return;
    }
    if (!hookUrl) {
        window.showAlert('Setup Missing', 'Please verify your Make fetch connection hook settings inside Tab 4.', 'error');
        return;
    }
    if (!pastedDescription) {
        window.showAlert('Form Incomplete', 'Please paste the job description text block to run an analysis.', 'error');
        return;
    }

    const loadingState = document.getElementById('loading-state');
    const resultsContainer = document.getElementById('results-container');
    const bulkPanel = document.getElementById('bulk-controls-panel');

    document.getElementById('empty-state').classList.add('hidden');
    if (resultsContainer) resultsContainer.classList.add('hidden');
    if (bulkPanel) bulkPanel.classList.add('hidden');

    let baseCVText = "";
    try {
        baseCVText = await fetchBaseCVText(hookUrl, loadingState);
    } catch (err) {
        if (loadingState) loadingState.classList.add('hidden');
        document.getElementById('empty-state').classList.remove('hidden');
        window.showAlert('Drive Sync Failed', err.message, 'error');
        return;
    }

    if (loadingState) {
        document.getElementById('loader-title').textContent = "Auditing Raw Text Description...";
        document.getElementById('loader-desc').textContent = `Evaluating metrics using chosen resume focus frame: ${chosenProfile}.`;
    }

    const technicalInstructionText = `You are an internal skillset compliance engine. Analyze the appended Job Description text block against the provided Candidate Base CV text block.

CRITICAL CORE FOCUS MODALITY:
The candidate is optimizing specifically for a "${chosenProfile}" track framework assignment. Measure compliance, matching keywords, missing tools, and gap ratios focused purely on this domain lens.

METADATA INFERENCE INSTRUCTIONS:
- Position Title Provided: ${typedTitle ? typedTitle : "NOT PROVIDED. You must analyze the text block and determine the exact job title. If impossible to determine, return an empty string \"\" explicitly."}
- Company Provided: ${typedCompany ? typedCompany : "NOT PROVIDED. You must analyze the text block and determine the hiring company or studio name. If impossible to determine, return an empty string \"\" explicitly."}

CRITICAL STRUCTURAL OUTPUT INSTRUCTIONS:
You MUST respond with a valid, single-item raw JSON array containing exactly one object matching the schema layout below.
DO NOT use markdown code wraps like \`\`\`json, write no preambles, and return nothing but the raw structural array text.

Schema Layout Expected:
[
  {
    "profile": "${chosenProfile}",
    "job_title": "String - Use the provided title, or your inferred title. If completely unknown, return an empty string \"\" explicitly.",
    "company": "String - Use the provided company, or your inferred company. If completely unknown, return an empty string \"\" explicitly.",
    "location": "Manual Text Audit",
    "link": "Manual Upload",
    "summary": "String - A highly concise 3-4 sentence high-level responsibility summary for the UI card",
    "description": "PLACEHOLDER",
    "match_score": Number,
    "skills_gaps": ["String - Missing tools/methodologies"],
    "resources": ["String - Preparation paths"]
  }
]`;

    let rawJSONText = "";
    try {
        const targetUrl = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${activeKey}`;

        const apiResponse = await window.fetch(targetUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contents: [{
                    parts: [
                        { text: technicalInstructionText },
                        { text: `CANDIDATE BASE CV PROFILE:\n${baseCVText}` },
                        { text: `TARGET JOB DESCRIPTION TO ANALYZE:\n${pastedDescription}` }
                    ]
                }]
            })
        });

        if (!apiResponse.ok) {
            const errData = await apiResponse.json();
            throw new Error(errData.error?.message || `Gemini gateway rejected text matrix mapping with code ${apiResponse.status}`);
        }

        const resData = await apiResponse.json();
        rawJSONText = resData.candidates?.[0]?.content?.parts?.[0]?.text;

        if (!rawJSONText) throw new Error("Could not process analysis parameters from pasted text contents.");

        rawJSONText = rawJSONText.replace(/^```json\s*/i, '').replace(/```\s*$/, '').trim();

        if (!rawJSONText.startsWith('[') && !rawJSONText.startsWith('{')) {
            throw new Error("Invalid response format generated by the AI parser.");
        }

        const singleJobArray = JSON.parse(rawJSONText);

        singleJobArray[0].profile = chosenProfile;
        if (typedTitle) singleJobArray[0].job_title = typedTitle;
        if (typedCompany) singleJobArray[0].company = typedCompany;
        if (typedUrl) singleJobArray[0].link = typedUrl;
        singleJobArray[0].description = pastedDescription;

        window.renderJobCards(singleJobArray);

        titleEl.value = '';
        companyEl.value = '';
        if (urlEl) urlEl.value = '';
        descEl.value = '';

        if (loadingState) loadingState.classList.add('hidden');
        if (resultsContainer) resultsContainer.classList.remove('hidden');
        if (bulkPanel) bulkPanel.classList.remove('hidden');
        window.updateSelectedCounter();

        window.showAlert('Analysis Complete', `Calculated match metrics under focus: ${chosenProfile}!`, 'success');
    } catch (error) {
        if (loadingState) loadingState.classList.add('hidden');
        document.getElementById('empty-state').classList.remove('hidden');
        window.showAlert('Text Processing Failure', `${error.message}`, 'error');
    }
}
