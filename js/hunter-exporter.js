import { updateSelectedCounter } from './hunter-ui.js';

export async function exportJobsToTracker(targetJobs = null) {
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
        const response = await window.fetch('/api/matches', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jobs: payload })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error || `Local API rejected payload with status code: ${response.status}`);
        }

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
        window.showAlert('Export Succeeded', `Staged ${payload.length} role(s) — check the Staged Matches tab.`, 'success');

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
