/**
 * Careers Hub Analyzer Module — v4.0 (Production Hardened)
 * Handles batch crawling and evaluation of corporate career boards.
 */

import { getPostingSourceValue } from './hunter-config.js';

export async function analyzeCareersHub() {
    const hubUrl = document.getElementById('hub-analysis-url').value.trim();
    const profile = document.getElementById('hub-analysis-profile').value;
    const extraFields = {
        applied_through: document.getElementById('hub-analysis-applied-through')?.value.trim() || undefined,
        posting_source: getPostingSourceValue('hub-analysis-posting-source') || undefined
    };

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

    try {
        const response = await fetch('/api/gemini/analyze-hub', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: hubUrl, profile })
        });
        const jobs = await response.json();
        if (!response.ok) {
            throw new Error(jobs.error || `Hub scan request failed with status ${response.status}`);
        }
        processDiscoveredJobs(jobs, extraFields);
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
function processDiscoveredJobs(rawJobsArray, extraFields = {}) {
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
            skills_gaps: cleanedGaps,
            _reposted: job._reposted || false,
            ...extraFields
        };
    });

    // 1. Force DOM wrapper visibility panels to expand (window.currentJobsList itself
    // gets set by appendJobCards below, merged with whatever's already accumulated —
    // it must NOT be overwritten here first, or prior audits would be wiped).
    const resultsContainer = document.getElementById('results-container');
    const emptyState = document.getElementById('empty-state');
    const bulkBar = document.getElementById('bulk-controls-panel');
    const resultsCount = document.getElementById('results-count');
    
    if (resultsContainer) resultsContainer.classList.remove('hidden');
    if (bulkBar) bulkBar.classList.remove('hidden');
    if (emptyState) emptyState.classList.add('hidden');
    if (resultsCount) resultsCount.textContent = `${normalizedJobs.length} Roles Discovered`;

    // 2. Fire layout engine — appended (not replaced) so hub results stack alongside
    // any other manual audits already on screen, matching the Verbatim/URL panels.
    if (typeof window.appendJobCards === 'function') {
        try {
            console.log("🎮 Rendering saturated array to UI. Object footprint map:", normalizedJobs[0]);
            window.appendJobCards(normalizedJobs);
        } catch (renderError) {
            console.error("❌ uiManager processing fault:", renderError);
            window.showAlert('Render Fault', `UI engine failed to compile layout: ${renderError.message}`, 'error');
        }
    } else {
        window.showAlert('Rendering Error', 'The UI layout manager render engine was not found.', 'error');
    }
}