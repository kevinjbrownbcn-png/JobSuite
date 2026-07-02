import { updateSelectedCounter, addToHistoryLog } from './hunter-ui.js';

export async function exportJobsToTracker(targetJobs = null) {
    const exportHookUrl = localStorage.getItem('export_webhook') || '';

    if (!exportHookUrl) {
        window.showAlert(
            'Configuration Missing',
            'No export target webhook found inside Tab 3 tracking sheet settings or hardcoded fallback.',
            'error'
        );
        return;
    }

    let payload = [];
    if (targetJobs) {
        payload = Array.isArray(targetJobs) ? targetJobs : [targetJobs];
    } else {
        const checkedBoxes = Array.from(document.querySelectorAll('.job-card-checkbox:checked'));
        payload = checkedBoxes.map(cb => {
            const cardElement = cb.closest('.job-card');
            return cardElement ? JSON.parse(cardElement.dataset.jobData || '{}') : null;
        }).filter(item => item !== null && Object.keys(item).length > 0);
    }

    if (payload.length === 0) {
        window.showAlert('Selection Empty', 'Please select at least one job posting card to export.', 'warning');
        return;
    }

    const exportBtn = document.getElementById('bulk-export-btn');
    const originalBtnText = exportBtn ? exportBtn.innerHTML : 'Export Selected';
    if (exportBtn) {
        exportBtn.disabled = true;
        exportBtn.innerHTML = `<span class="spinner"></span> Transmitting data rows...`;
    }

    try {
        const response = await window.fetch(exportHookUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jobs: payload })
        });

        if (!response.ok) {
            throw new Error(`Data synchronization pipeline rejected payload with status code: ${response.status}`);
        }

        const dedupRegistry = JSON.parse(localStorage.getItem('hunter_dedup_registry')) || {};
        const timestamp = new Date().getTime();

        payload.forEach(job => {
            if (job.job_title && job.company) {
                const signatureKey = `${job.job_title.toLowerCase().trim()}_${job.company.toLowerCase().trim()}`;
                dedupRegistry[signatureKey] = timestamp;
            }
            addToHistoryLog(job.job_title, job.company, job.link, job.location, job.match_score);
        });
        localStorage.setItem('hunter_dedup_registry', JSON.stringify(dedupRegistry));

        if (!targetJobs) {
            document.querySelectorAll('.job-card-checkbox:checked').forEach(cb => {
                const card = cb.closest('.job-card');
                if (card) card.remove();
            });

            const remainingCards = document.querySelectorAll('.job-card');
            if (remainingCards.length === 0) {
                document.getElementById('results-container').classList.add('hidden');
                document.getElementById('bulk-controls-panel').classList.add('hidden');
                document.getElementById('empty-state').classList.remove('hidden');
            }
        }

        updateSelectedCounter();
        window.showAlert('Export Succeeded', `Successfully synced ${payload.length} rows to your tracking sheet pipeline!`, 'success');

    } catch (err) {
        console.error("Transmission Error:", err);
        window.showAlert('Sync Transfer Interrupted', err.message, 'error');
    } finally {
        if (exportBtn) {
            exportBtn.disabled = false;
            exportBtn.innerHTML = originalBtnText;
        }
    }
}

window.exportJobsToTracker = exportJobsToTracker;
