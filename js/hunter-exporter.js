import { updateSelectedCounter, renderJobCards } from './hunter-ui.js';

function jobSignature(job) {
    if (!job || !job.job_title || !job.company) return null;
    return `${job.job_title.toLowerCase().trim()}_${job.company.toLowerCase().trim()}`;
}

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

        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(result.error || `Local API rejected payload with status code: ${response.status}`);
        }

        // Drop exported jobs out of the accumulated list (matched by title+company,
        // same identity key used everywhere else) and re-render what's left — this is
        // what makes the accumulated Manual Audit list not resurrect already-exported
        // postings the next time something new gets appended to it.
        const exportedSignatures = new Set(payload.map(jobSignature).filter(Boolean));
        const remaining = (window.currentJobsList || []).filter(job => {
            const sig = jobSignature(job);
            return sig === null || !exportedSignatures.has(sig);
        });
        renderJobCards(remaining);

        updateSelectedCounter();

        let message = `Staged ${payload.length} role(s) — check the Staged Matches tab.`;
        if (result._auto_docgen_sent?.length) {
            message += ` ${result._auto_docgen_sent.length} sent straight to Doc Creation (90%+ match).`;
        }
        if (result._auto_docgen_failed?.length) {
            message += ` ${result._auto_docgen_failed.length} high-match job(s) stayed at Draft — doc generation failed, retry from Staged Matches.`;
        }
        window.showAlert('Export Succeeded', message, 'success');

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
