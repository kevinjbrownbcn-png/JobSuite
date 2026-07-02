/**
 * Careers Hub Analyzer Module — v4.0 (Production Hardened)
 * Handles batch crawling and evaluation of corporate career boards.
 */

export async function analyzeCareersHub() {
    const hubUrl = document.getElementById('hub-analysis-url').value.trim();
    const profile = document.getElementById('hub-analysis-profile').value;
    
    if (!hubUrl) {
        window.showAlert('Input Missing', 'Please provide a valid corporate careers portal URL link.', 'warning');
        return;
    }

    // 1. INSTANT TAB SWITCH: Jump to the scanner page immediately when the crawl begins
    if (typeof window.switchTab === 'function') {
        window.switchTab('hunt');
    }

    // 2. Initialize loading screen states on the target tab view
    const loader = document.getElementById('loading-state');
    const loaderTitle = document.getElementById('loader-title');
    const loaderDesc = document.getElementById('loader-desc');
    
    if (loader) loader.classList.remove('hidden');
    if (loaderTitle) loaderTitle.textContent = "Crawling Careers Hub...";
    if (loaderDesc) loaderDesc.textContent = "Harvesting individual vacancy links and dispatching data structures to the AI match matrix.";

    // 3. Direct Environment Detection
    const hasPyBridge = window.pywebview && window.pywebview.api;

    try {
        if (hasPyBridge) {
            if (typeof window.pywebview.api.batch_scan_careers_hub !== 'function') {
                throw new Error("The backend API method 'batch_scan_careers_hub' is missing or improperly exposed in Python.");
            }

            const rawResponse = await window.pywebview.api.batch_scan_careers_hub(hubUrl, profile);
            
            let data;
            if (typeof rawResponse === 'string') {
                data = JSON.parse(rawResponse);
            } else {
                data = rawResponse;
            }
            
            if (data && data.status === "success" && Array.isArray(data.jobs)) {
                processDiscoveredJobs(data.jobs);
            } else {
                window.showAlert('Scan Failed', (data && data.message) || 'An unknown structural error occurred.', 'error');
            }
        } 
        else {
            console.warn("⚠️ PyWebView environment not found. Executing simulated UI loop parsing path.");
            await new Promise(resolve => setTimeout(resolve, 1200));

            const mockJobs = [
                {
                    job_title: "Localization Engineer (v4.0 Sandbox View)",
                    company: "Translated Studio Mock",
                    location: "Spain (Remote)",
                    match_score: 94,
                    summary: "Responsible for engineering localization pipelines, regex filters, and parsing software code repositories for international delivery markets.",
                    skills_gaps: [],
                    link: hubUrl
                }
            ];
            processDiscoveredJobs(mockJobs);
        }
    } catch (err) {
        console.error("❌ Hub Scan Execution Fault Error:", err);
        window.showAlert('Execution Error', `Pipeline error: ${err.message}`, 'error');
    } finally {
        if (loader) loader.classList.add('hidden');
    }
}

/**
 * Saturates the job payload data structure with all syntax variants
 * to fully bypass strict filters inside uiManager.js.
 */
function processDiscoveredJobs(rawJobsArray) {
    if (!rawJobsArray || rawJobsArray.length === 0) {
        window.showAlert('No Jobs Found', 'The hub scan completed but found no valid openings.', 'warning');
        return;
    }

    // Clean text helper to prevent breaking characters
    const cleanText = (str) => {
        if (!str) return "";
        return str
            .replace(/[\u2018\u2019]/g, "'")
            .replace(/[\u201C\u201D]/g, '"')
            .replace(/[\u2014\u2015]/g, "—")
            .replace(/\\u[0-9a-fA-F]{4}/g, "")
            .trim();
    };

    // DATA LAYER SHAPE SATURATION INJECTOR
    const normalizedJobs = rawJobsArray.map(job => {
        // Resolve raw properties
        const rawTitle = job.job_title || job.jobTitle || job.title || "Untitled Position";
        const rawCompany = job.company || "Unknown Company";
        const rawLocation = job.location || "Remote / Worldwide";
        const rawSummary = job.summary || "No assessment breakdown generated.";
        
        let rawScore = 50;
        if (job.match_score !== undefined) rawScore = job.match_score;
        else if (job.matchScore !== undefined) rawScore = job.matchScore;
        else if (job.score !== undefined) rawScore = job.score;
        
        const finalizedScore = parseInt(rawScore, 10);

        // Standardize gaps arrays
        let gaps = job.skills_gaps || job.skillsGaps || job.gaps || [];
        if (!Array.isArray(gaps)) gaps = [gaps.toString()];
        const cleanedGaps = gaps.map(g => cleanText(g)).filter(g => g.length > 0);

        const textTitle = cleanText(rawTitle);
        const textCompany = cleanText(rawCompany);
        const textLocation = cleanText(rawLocation);
        const textSummary = cleanText(rawSummary);

        return {
            job_title: textTitle,
            company: textCompany,
            location: textLocation,
            link: job.link || "",
            match_score: finalizedScore,
            summary: textSummary,
            skills_gaps: cleanedGaps
        };
    });

    // 1. Commit state back to application global memory arrays cache
    window.currentJobsList = normalizedJobs; 
    
    // 2. Force DOM wrapper visibility panels to expand
    const resultsContainer = document.getElementById('results-container');
    const emptyState = document.getElementById('empty-state');
    const bulkBar = document.getElementById('bulk-controls-panel');
    const resultsCount = document.getElementById('results-count');
    
    if (resultsContainer) resultsContainer.classList.remove('hidden');
    if (bulkBar) bulkBar.classList.remove('hidden');
    if (emptyState) emptyState.classList.add('hidden');
    if (resultsCount) resultsCount.textContent = `${normalizedJobs.length} Roles Discovered`;

    // 3. Fire layout engine
    if (typeof window.renderJobCards === 'function') {
        try {
            console.log("🎮 Rendering saturated array to UI. Object footprint map:", normalizedJobs[0]);
            window.renderJobCards(normalizedJobs);
        } catch (renderError) {
            console.error("❌ uiManager processing fault:", renderError);
            window.showAlert('Render Fault', `UI engine failed to compile layout: ${renderError.message}`, 'error');
        }
    } else {
        window.showAlert('Rendering Error', 'The UI layout manager render engine was not found.', 'error');
    }
}