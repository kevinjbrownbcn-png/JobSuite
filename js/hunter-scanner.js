import { renderJobCards, updateSelectedCounter } from './hunter-ui.js';

export async function scanWebForJobs() {
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

    document.getElementById('loader-title').textContent = "Harvesting Open Web Postings...";
    document.getElementById('loader-desc').textContent = "Analyzing job markets, ranking criteria matches, and checking framework skill gaps.";
    loadingState.classList.remove('hidden');

    const location = document.getElementById('search-location').value;
    const timeWindow = document.getElementById('search-time').value;
    const focusKeywords = document.getElementById('search-focus').value;

    try {
        const response = await fetch('/api/gemini/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ roles: checkedRoles, location, time_window: timeWindow, focus: focusKeywords })
        });
        const jobs = await response.json();
        if (!response.ok) {
            throw new Error(jobs.error || `Scan request failed with status ${response.status}`);
        }

        // Dedup against already-staged/applied postings now happens server-side
        // (against the real `matches` table), so both this UI and Streamlit see the
        // same filtering — no client-side registry to maintain here anymore.
        renderJobCards(jobs);
        loadingState.classList.add('hidden');
        resultsContainer.classList.remove('hidden');

        if (jobs.length > 0) {
            bulkPanel.classList.remove('hidden');
            updateSelectedCounter();
            window.showAlert('Scan Completed', `Successfully found and analyzed ${jobs.length} new roles!`, 'success');
        } else {
            document.getElementById('empty-state').classList.remove('hidden');
            window.showAlert('Scan Completed', 'Discovered roles match recent exports and were filtered.', 'info');
        }

    } catch (error) {
        loadingState.classList.add('hidden');
        document.getElementById('empty-state').classList.remove('hidden');
        window.showAlert('Web Scraper Engine Interrupted', `${error.message}`, 'error');
    }
}

window.scanWebForJobs = scanWebForJobs;
