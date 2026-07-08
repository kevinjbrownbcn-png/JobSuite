import { getPostingSourceValue } from './hunter-config.js';

export async function analyzeManualURL() {
    const urlInputElement = document.getElementById('direct-analysis-url');
    const profileSelector = document.getElementById('direct-analysis-profile');
    if (!urlInputElement || !profileSelector) return;

    const targetURL = urlInputElement.value.trim();
    const chosenProfile = profileSelector.value;

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

    document.getElementById('loader-title').textContent = "Reading Target Webpage...";
    document.getElementById('loader-desc').textContent = `Extracting job specifications tailored to profile context framework: ${chosenProfile}.`;
    if (loadingState) loadingState.classList.remove('hidden');

    try {
        const response = await fetch('/api/gemini/analyze-url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: targetURL, profile: chosenProfile })
        });
        const job = await response.json();
        if (!response.ok) {
            throw new Error(job.error || `Analysis request failed with status ${response.status}`);
        }

        const singleJobArray = [job];
        singleJobArray[0].profile = chosenProfile;
        singleJobArray[0].applied_through = document.getElementById('direct-analysis-applied-through')?.value.trim() || undefined;
        singleJobArray[0].posting_source = getPostingSourceValue('direct-analysis-posting-source') || undefined;

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

    if (loadingState) {
        document.getElementById('loader-title').textContent = "Auditing Raw Text Description...";
        document.getElementById('loader-desc').textContent = `Evaluating metrics using chosen resume focus frame: ${chosenProfile}.`;
        loadingState.classList.remove('hidden');
    }

    try {
        const response = await fetch('/api/gemini/analyze-text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                description: pastedDescription, profile: chosenProfile,
                title: typedTitle, company: typedCompany
            })
        });
        const job = await response.json();
        if (!response.ok) {
            throw new Error(job.error || `Analysis request failed with status ${response.status}`);
        }

        const singleJobArray = [job];
        singleJobArray[0].profile = chosenProfile;
        if (typedTitle) singleJobArray[0].job_title = typedTitle;
        if (typedCompany) singleJobArray[0].company = typedCompany;
        if (typedUrl) singleJobArray[0].link = typedUrl;
        singleJobArray[0].description = pastedDescription;
        singleJobArray[0].applied_through = document.getElementById('manual-text-applied-through')?.value.trim() || undefined;
        singleJobArray[0].posting_source = getPostingSourceValue('manual-text-posting-source') || undefined;

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
