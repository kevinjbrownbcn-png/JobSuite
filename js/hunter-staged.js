// Staged Matches — replaces the old localStorage export-history ledger with the
// real, persisted `matches` table. Lifecycle: Draft -> New -> Processed -> Applied ->
// Migrated to Tracker, or Draft/New/Processed -> Discarded -> Purged.

function escapeHTML(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Continuous red (0%) -> yellow (50%) -> green (100%) scale, matching the color-scale
// conditional formatting the match scores used to have in the spreadsheet.
function scoreToColor(score) {
    if (score === null || score === undefined || score === '' || isNaN(score)) return 'var(--text-muted)';
    const pct = Math.max(0, Math.min(100, Number(score))) / 100;
    return `hsl(${pct * 120}, 70%, 45%)`;
}

const STATUS_LABELS = {
    'Draft':               { text: 'Draft',           color: 'var(--text-muted)' },
    'New':                 { text: 'Queued for Prep',  color: 'var(--accent-amber)' },
    'Processed':           { text: 'Docs Ready',       color: '#38bdf8' },
    'Applied':             { text: 'Applied',          color: 'var(--accent-purple)' },
    'Migrated to Tracker': { text: '✓ In Tracker', color: 'var(--success)' },
    'Discarded':           { text: 'Discarding…',     color: 'var(--warning)' },
    'Purged':              { text: 'Discarded',        color: 'var(--text-muted)' },
    'N/A':                 { text: 'N/A',               color: 'var(--text-muted)' }
};

async function patchMatch(id, statusValue, loadingMessage) {
    const loader = document.getElementById('loading-state');
    const loaderTitle = document.getElementById('loader-title');
    const loaderDesc = document.getElementById('loader-desc');
    if (loader) {
        loader.classList.remove('hidden');
        if (loaderTitle) loaderTitle.textContent = loadingMessage;
        if (loaderDesc) loaderDesc.textContent = 'Waiting for Make.com to finish and respond — this can take a little while.';
    }

    try {
        const response = await fetch(`/api/matches/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: statusValue })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);

        if (data._discard_warning) {
            window.showAlert('Discarded (cleanup pending)', `Marked as Discarded, but the Drive cleanup didn't run: ${data._discard_warning}. You can leave it — it'll stay Discarded until cleanup succeeds.`, 'warning');
        } else {
            window.showAlert('Updated', `Match moved to "${data.status}".`, 'success');
        }
        await renderStagedMatchesTable();
    } catch (err) {
        window.showAlert('Update Failed', err.message, 'error');
    } finally {
        if (loader) loader.classList.add('hidden');
    }
}

async function discardMatch(id) {
    if (!window.confirm('Discard this staged match? Its generated CV/cover letter (if any) will be trashed in Drive.')) return;
    await patchMatch(id, 'Discarded', 'Discarding match, cleaning up generated docs…');
}

function toggleDescriptionEditor(match, rowEl) {
    const next = rowEl.nextElementSibling;
    if (next && next.classList.contains('desc-editor-row')) {
        next.remove();
        return;
    }
    document.querySelectorAll('.desc-editor-row').forEach(el => el.remove());

    const editorRow = document.createElement('tr');
    editorRow.className = 'desc-editor-row';

    const td = document.createElement('td');
    td.colSpan = 4;
    td.style.cssText = 'padding: 12px; background: var(--nav-underlay);';

    const descLabel = document.createElement('div');
    descLabel.textContent = 'Job Description';
    descLabel.style.cssText = 'font-size:11px; font-weight:600; color:var(--text-muted); margin-bottom:4px;';

    const textarea = document.createElement('textarea');
    textarea.value = match.job_description || '';
    textarea.placeholder = 'No job description on file.';
    textarea.style.cssText = 'width:100%; min-height:140px; background:var(--panel); color:var(--text-main); border:1px solid var(--border); border-radius:6px; padding:8px; font-size:12px; font-family:inherit; box-sizing:border-box; resize:vertical;';

    const notesLabel = document.createElement('div');
    notesLabel.textContent = 'Special Instructions (considered when generating docs)';
    notesLabel.style.cssText = 'font-size:11px; font-weight:600; color:var(--text-muted); margin:10px 0 4px;';

    const notesTextarea = document.createElement('textarea');
    notesTextarea.value = match.notes || '';
    notesTextarea.placeholder = 'e.g. "Posting says on-site/hybrid — request remote consideration in the cover letter."';
    notesTextarea.style.cssText = 'width:100%; min-height:60px; background:var(--panel); color:var(--text-main); border:1px solid var(--border); border-radius:6px; padding:8px; font-size:12px; font-family:inherit; box-sizing:border-box; resize:vertical;';

    const btnRow = document.createElement('div');
    btnRow.style.cssText = 'margin-top:8px; display:flex; gap:8px;';

    const saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.style.cssText = 'background:#0d9488;color:#fff;border:none;padding:6px 14px;border-radius:4px;font-size:11px;cursor:pointer;font-weight:600;';
    saveBtn.onclick = async () => {
        try {
            const response = await fetch(`/api/matches/${match.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_description: textarea.value, notes: notesTextarea.value })
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
            window.showAlert('Saved', 'Description and instructions updated.', 'success');
            await renderStagedMatchesTable();
        } catch (err) {
            window.showAlert('Save Failed', err.message, 'error');
        }
    };

    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText = 'background:none;color:var(--text-muted);border:1px solid var(--border);padding:6px 14px;border-radius:4px;font-size:11px;cursor:pointer;';
    cancelBtn.onclick = () => editorRow.remove();

    btnRow.append(saveBtn, cancelBtn);
    td.append(descLabel, textarea, notesLabel, notesTextarea, btnRow);
    editorRow.appendChild(td);
    rowEl.after(editorRow);
}

// Cached from the last fetch, so toggling a filter dropdown re-renders instantly
// without another round-trip — same pattern dashboard-viewer.js uses.
let cachedMatches = [];

function populateStagedFilterOptions(matches) {
    const statusSelect = document.getElementById('staged-filter-status');
    const companySelect = document.getElementById('staged-filter-company');
    if (!statusSelect || !companySelect) return;

    const prevStatus = statusSelect.value || 'ALL';
    const prevCompany = companySelect.value || 'ALL';

    const statuses = [...new Set(matches.map(m => m.status).filter(Boolean))].sort();
    const companies = [...new Set(matches.map(m => m.company).filter(Boolean))].sort();

    statusSelect.innerHTML = '<option value="ALL">All Statuses</option>' +
        statuses.map(s => `<option value="${escapeHTML(s)}">${escapeHTML((STATUS_LABELS[s] || { text: s }).text)}</option>`).join('');
    companySelect.innerHTML = '<option value="ALL">All Companies</option>' +
        companies.map(c => `<option value="${escapeHTML(c)}">${escapeHTML(c)}</option>`).join('');

    // Restore the previous selection if it's still a valid option (the underlying
    // data changed, e.g. after a status update), otherwise fall back to "ALL".
    statusSelect.value = statuses.includes(prevStatus) || prevStatus === 'ALL' ? prevStatus : 'ALL';
    companySelect.value = companies.includes(prevCompany) || prevCompany === 'ALL' ? prevCompany : 'ALL';
}

export async function renderStagedMatchesTable() {
    const tbody = document.getElementById('staged-matches-tbody');
    if (!tbody) return;

    try {
        const response = await fetch('/api/matches');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        cachedMatches = await response.json();
    } catch (err) {
        console.error('Failed to load staged matches:', err);
        if (window.showAlert) window.showAlert('Load Failed', `Could not load staged matches: ${err.message}`, 'error');
        return;
    }

    populateStagedFilterOptions(cachedMatches || []);
    filterAndRenderStagedMatches();
}

export function filterAndRenderStagedMatches() {
    const tbody = document.getElementById('staged-matches-tbody');
    const emptyState = document.getElementById('staged-matches-empty');
    if (!tbody) return;

    const statusFilter = document.getElementById('staged-filter-status')?.value || 'ALL';
    const companyFilter = document.getElementById('staged-filter-company')?.value || 'ALL';

    const matches = (cachedMatches || []).filter(m =>
        (statusFilter === 'ALL' || m.status === statusFilter) &&
        (companyFilter === 'ALL' || m.company === companyFilter)
    );

    const countEl = document.getElementById('staged-matches-count');
    if (countEl) countEl.textContent = matches.length;

    tbody.innerHTML = '';

    if (!cachedMatches || cachedMatches.length === 0) {
        if (emptyState) emptyState.classList.remove('hidden');
        return;
    }
    if (emptyState) emptyState.classList.add('hidden');

    matches.forEach(match => {
        const row = document.createElement('tr');
        const statusInfo = STATUS_LABELS[match.status] || { text: match.status, color: 'var(--text-muted)' };
        const safeLink = match.job_url && match.job_url.startsWith('http') ? match.job_url : null;

        const tdTitle = document.createElement('td');
        tdTitle.innerHTML = `<span style="font-weight:600; color:var(--text-main);">${escapeHTML(match.job_title)}</span><br><span style="color:var(--text-muted); font-size:11px;">${escapeHTML(match.company)}</span>`;

        const tdScore = document.createElement('td');
        tdScore.style.textAlign = 'center';
        tdScore.innerHTML = `<span style="color:${scoreToColor(match.match_score)}; font-weight:bold;">${escapeHTML(String(match.match_score ?? '—'))}%</span>`;

        // Same visual treatment as the Action column's buttons: dark fill, colored
        // text, matching colored border — texts/colors themselves come from STATUS_LABELS.
        const tdStatus = document.createElement('td');
        tdStatus.innerHTML = `<span style="display:inline-block; background:var(--panel); color:${statusInfo.color}; border:1px solid ${statusInfo.color}; padding:4px 10px; border-radius:4px; font-size:11px; font-weight:600;">${escapeHTML(statusInfo.text)}</span>`;

        const tdAction = document.createElement('td');
        tdAction.style.textAlign = 'right';

        if (safeLink) {
            const linkA = document.createElement('a');
            linkA.href = safeLink;
            linkA.target = '_blank';
            linkA.style.cssText = 'color:#38bdf8;text-decoration:none;font-size:11px;margin-right:10px;';
            linkA.textContent = 'View ↗';
            tdAction.appendChild(linkA);
        }

        const descBtn = document.createElement('button');
        descBtn.style.cssText = 'background:var(--panel);color:var(--text-muted);border:1px solid var(--border);padding:4px 10px;border-radius:4px;font-size:11px;cursor:pointer;font-weight:600;margin-right:6px;';
        descBtn.textContent = 'Edit Details';
        descBtn.onclick = () => toggleDescriptionEditor(match, row);
        tdAction.appendChild(descBtn);

        if (match.status === 'Draft' || match.status === 'New') {
            const btn = document.createElement('button');
            btn.style.cssText = 'background:var(--panel);color:var(--accent-amber);border:1px solid var(--accent-amber);padding:4px 10px;border-radius:4px;font-size:11px;cursor:pointer;font-weight:600;margin-right:6px;';
            btn.textContent = match.status === 'New' ? 'Retry: Send to Prep' : 'Send to Prep';
            btn.onclick = () => patchMatch(match.id, 'New', 'Requesting CV/cover letter generation…');
            tdAction.appendChild(btn);
        } else if (match.status === 'Processed') {
            const regenBtn = document.createElement('button');
            regenBtn.style.cssText = 'background:var(--panel);color:#38bdf8;border:1px solid #38bdf8;padding:4px 10px;border-radius:4px;font-size:11px;cursor:pointer;font-weight:600;margin-right:6px;';
            regenBtn.textContent = 'Regenerate Docs';
            regenBtn.onclick = () => {
                if (!window.confirm('Regenerate the CV/cover letter? This creates a new set of docs alongside the existing ones — it does not overwrite them.')) return;
                patchMatch(match.id, 'New', 'Re-pushing content to Docs…');
            };
            tdAction.appendChild(regenBtn);

            const btn = document.createElement('button');
            btn.style.cssText = 'background:var(--panel);color:var(--accent-purple);border:1px solid var(--accent-purple);padding:4px 10px;border-radius:4px;font-size:11px;cursor:pointer;font-weight:600;margin-right:6px;';
            btn.textContent = 'Mark as Applied';
            btn.onclick = () => patchMatch(match.id, 'Applied', 'Recording application…');
            tdAction.appendChild(btn);
        }

        if (!['Migrated to Tracker', 'Purged'].includes(match.status)) {
            const discardBtn = document.createElement('button');
            discardBtn.style.cssText = 'background:none;color:var(--error);border:1px solid var(--error);padding:4px 10px;border-radius:4px;font-size:11px;cursor:pointer;font-weight:600;';
            discardBtn.textContent = match.status === 'Discarded' ? 'Retry Cleanup' : 'Discard';
            discardBtn.onclick = () => discardMatch(match.id);
            tdAction.appendChild(discardBtn);
        }

        row.append(tdTitle, tdScore, tdStatus, tdAction);
        tbody.appendChild(row);
    });
}
