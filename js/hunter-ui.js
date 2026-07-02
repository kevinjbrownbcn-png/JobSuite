// Shared application-wide runtime variables
let selectedJobsIndices = new Set();

function escapeHTML(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

export function updateSelectedCounter() {
    const totalCards = document.querySelectorAll('.job-card').length;
    const checkedCards = document.querySelectorAll('.job-card-checkbox:checked').length;
    
    const counterText = document.getElementById('selected-counter-text');
    if (counterText) {
        counterText.textContent = `${checkedCards} of ${totalCards} selected`;
    }
}

export function toggleSelectAll(masterCheckbox) {
    const checkboxes = document.querySelectorAll('.job-card-checkbox');
    checkboxes.forEach(cb => {
        cb.checked = masterCheckbox.checked;
        const card = cb.closest('.job-card');
        if (card) {
            if (masterCheckbox.checked) {
                card.classList.add('selected');
            } else {
                card.classList.remove('selected');
            }
        }
    });
    updateSelectedCounter();
}

export function addCustomRoleOption() {
    const inputEl = document.getElementById('custom-role-input');
    if (!inputEl) return;
    
    const val = inputEl.value.trim();
    if (!val) return;

    const listContainer = document.getElementById('roles-checkbox-list');
    const customId = `custom-role-${Date.now()}`;

    const newLabel = document.createElement('label');
    newLabel.className = "checkbox-row";
    newLabel.innerHTML = `
        <input type="checkbox" id="${customId}" value="${val}" checked>
        <span>${val}</span>
    `;
    
    listContainer.appendChild(newLabel);
    inputEl.value = "";
    
    // Safely trigger backup configuration saves natively
    const changeEvent = new Event('change');
    newLabel.querySelector('input').dispatchEvent(changeEvent);
    
    window.showAlert('Custom Role Added', `"${val}" has been added to your discovery checklist.`, 'success');
}

export function saveParamState() {
    const roleCheckboxes = document.querySelectorAll('#roles-checkbox-list input[type="checkbox"]');
    const rolesData = Array.from(roleCheckboxes).map(cb => ({
        id: cb.id,
        value: cb.value,
        checked: cb.checked,
        isCustom: cb.id.startsWith('custom-role-')
    }));

    const locationEl = document.getElementById('search-location');
    const timeEl = document.getElementById('search-time');
    const focusEl = document.getElementById('search-focus');

    const statePayload = {
        roles: rolesData,
        location: locationEl ? locationEl.value : '',
        time: timeEl ? timeEl.value : 'the last 7 days',
        focus: focusEl ? focusEl.value : ''
    };

    localStorage.setItem('job_hunter_param_state', JSON.stringify(statePayload));
}

async function checkCardUrl(pillEl, url) {
    if (!window.pywebview || !window.pywebview.api) {
        pillEl.style.display = 'none';
        return;
    }
    try {
        const raw = await window.pywebview.api.check_url_status(url);
        const result = JSON.parse(raw);
        if (result.ok) {
            pillEl.textContent = '✓ Live';
            pillEl.className = 'link-status-pill link-status-live';
        } else if (result.status === 404) {
            pillEl.textContent = '✗ 404';
            pillEl.className = 'link-status-pill link-status-dead';
        } else if (result.error === 'timeout') {
            pillEl.textContent = '⚠ Timeout';
            pillEl.className = 'link-status-pill link-status-warn';
        } else {
            pillEl.textContent = `⚠ ${result.status || 'Error'}`;
            pillEl.className = 'link-status-pill link-status-warn';
        }
    } catch (e) {
        pillEl.textContent = '⚠ Error';
        pillEl.className = 'link-status-pill link-status-warn';
    }
}

export function renderJobCards(jobs) {
    const listContainer = document.getElementById('jobs-list');
    if (!listContainer) return;
    
    listContainer.innerHTML = "";
    window.currentJobsList = jobs; 
    
    const countBadge = document.getElementById('results-count');
    if (countBadge) countBadge.textContent = `${jobs.length} Roles Discovered`;

    if (!jobs || jobs.length === 0) {
        document.getElementById('results-container').classList.add('hidden');
        document.getElementById('bulk-controls-panel').classList.add('hidden');
        document.getElementById('empty-state').classList.remove('hidden');
        return;
    }

    // 1. Define the case-insensitive language exclusion regex (Excluding English)
    const languageExcludeRegex = /\b(German|Deutsch|French|Français|Spanish|Español|Italian|Italiano|Japanese|Chinese|Mandarin|Portuguese|Arabic)\b/i;

    let renderedCount = 0;

    jobs.forEach((job, index) => {
        // 2. Run the title screening check
        if (job.job_title && languageExcludeRegex.test(job.job_title)) {
            console.log(`[Filter] Skipped card "${job.job_title}" at index ${index} due to language exclusion rules.`);
            return; // Skip this iteration entirely
        }

        renderedCount++;

        const card = document.createElement('div');
        card.className = "job-card";
        card.dataset.jobData = JSON.stringify(job);

        // Dynamically compute score badge coloring
        let scoreColor = "#64748b";
        if (job.match_score >= 85) scoreColor = "#10b981";
        else if (job.match_score >= 70) scoreColor = "#eab308";
        else if (job.match_score > 0) scoreColor = "#ef4444";

        const skillGapsHTML = Array.isArray(job.skills_gaps) && job.skills_gaps.length > 0
            ? job.skills_gaps.map(g => `<span class="badge-gap">${escapeHTML(g)}</span>`).join('')
            : `<span style="color: #10b981; font-size: 12px; font-weight: bold;">✓ Perfect Toolkit Alignment</span>`;

        const safeLink = job.link && job.link.startsWith('http') ? job.link : null;

        card.innerHTML = `
            <div class="card-left-select">
                <input type="checkbox" class="job-card-checkbox" data-index="${index}" onchange="this.closest('.job-card').classList.toggle('selected', this.checked); window.updateSelectedCounter();">
            </div>
            <div style="flex-grow: 1; display: flex; flex-direction: column; gap: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;">
                    <div>
                        <h4 class="card-title">${escapeHTML(job.job_title) || 'Inferred Position'}</h4>
                        <p class="card-subtitle">${escapeHTML(job.company) || 'Unknown Studio'} — <span style="color: #94a3b8;">${escapeHTML(job.location) || 'Manual Text Audit'}</span></p>
                    </div>
                    <div class="card-score-badge" style="background-color: ${scoreColor};">${job.match_score || 0}% Match</div>
                </div>

                <p class="card-summary">${escapeHTML(job.summary) || ''}</p>

                <div class="gap-section">
                    <div class="gap-title">Skill Gaps Identified</div>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px;">${skillGapsHTML}</div>
                </div>

                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 8px; border-top: 1px solid #334155; padding-top: 8px;">
                    <div style="display: flex; align-items: center; gap: 0;">
                        ${safeLink
                            ? `<a href="${escapeHTML(safeLink)}" target="_blank" class="card-link-anchor" title="${escapeHTML(safeLink)}" style="margin: 0;">Open Original Job Website ↗</a><span class="link-status-pill link-status-checking">⏳</span>`
                            : '<span></span>'}
                    </div>
                    <button
                        class="single-export-btn"
                        style="background: #1e293b; color: #38bdf8; border: 1px solid #38bdf8; padding: 4px 10px; border-radius: 4px; font-size: 11px; cursor: pointer; font-weight: 600;"
                        onclick="window.exportJobsToTracker(window.currentJobsList[${index}])"
                    >
                        Sync to Tracker →
                    </button>
                </div>
            </div>
        `;
        listContainer.appendChild(card);

        if (safeLink) {
            const pill = card.querySelector('.link-status-pill');
            if (pill) checkCardUrl(pill, safeLink);
        }
    });

    // 3. Update badge count to accurately reflect only what is visible on screen
    if (countBadge) countBadge.textContent = `${renderedCount} Roles Discovered`;
    
    // 4. If all discovered jobs were language-filtered out, trigger empty-state view
    if (renderedCount === 0) {
        document.getElementById('results-container').classList.add('hidden');
        document.getElementById('bulk-controls-panel').classList.add('hidden');
        document.getElementById('empty-state').classList.remove('hidden');
    }
}


export function addToHistoryLog(title, company, link, location, score) {
    let history = [];
    try {
        history = JSON.parse(localStorage.getItem('job_hunter_audit_ledger') || '[]');
    } catch(e) { history = []; }

    history.unshift({
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        title: title,
        company: company,
        link: link,
        location: location,
        score: score
    });

    localStorage.setItem('job_hunter_audit_ledger', JSON.stringify(history.slice(0, 50)));
}

export function renderHistoryLogTable() {
    const tbody = document.getElementById('history-log-tbody');
    const emptyState = document.getElementById('history-empty-state');
    if (!tbody) return;

    let history = [];
    try {
        history = JSON.parse(localStorage.getItem('job_hunter_audit_ledger') || '[]');
    } catch(e) { history = []; }

    tbody.innerHTML = "";
    
    if (history.length === 0) {
        if (emptyState) emptyState.classList.remove('hidden');
        return;
    }

    if (emptyState) emptyState.classList.add('hidden');

    history.forEach(item => {
        const row = document.createElement('tr');
        const safeLink = item.link && item.link.startsWith('http') ? item.link : null;
        row.innerHTML = `
            <td style="color: #64748b; font-size: 11px;">${escapeHTML(item.timestamp)}</td>
            <td style="font-weight: 600; color: #f8fafc;">${escapeHTML(item.title)}</td>
            <td style="color: #cbd5e1;">${escapeHTML(item.company)}</td>
            <td style="color: #94a3b8; font-size: 12px;">${escapeHTML(item.location)}</td>
            <td style="text-align: center;"><span style="color: #2dd4bf; font-weight: bold;">${escapeHTML(String(item.score))}%</span></td>
            <td style="text-align: right;">
                ${safeLink
                    ? `<a href="${escapeHTML(safeLink)}" target="_blank" style="color: #38bdf8; text-decoration: none; font-size: 11px;">View Posting ↗</a>`
                    : `<span style="color: #475569; font-size: 11px;">No Link</span>`
                }
            </td>
        `;
        tbody.appendChild(row);
    });
}

export function clearHistoryLog() {
    localStorage.removeItem('job_hunter_audit_ledger');
    renderHistoryLogTable();
    window.showAlert('Ledger Cleared', 'All local historical spreadsheet logging arrays wiped clean.', 'success');
}

// Toast dismiss helper (also used by close buttons)
function dismissToast(toast) {
    toast.classList.remove('toast-visible');
    toast.classList.add('toast-hiding');
    setTimeout(() => toast.remove(), 320);
}

// System Toast Alerts Engine — persistent until closed, vertically stacked
window.showAlert = function(title, text, type = 'success') {
    const wrapper = document.getElementById('toast-wrapper-container');
    if (!wrapper) return;

    const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };

    const toast = document.createElement('div');
    toast.className = `toast-card toast-${type}`;

    const iconEl = document.createElement('div');
    iconEl.className = `toast-status-icon toast-icon-${type}`;
    iconEl.textContent = icons[type] || '✓';

    const content = document.createElement('div');
    content.className = 'toast-content';
    const h4 = document.createElement('h4');
    h4.textContent = title;
    const p = document.createElement('p');
    p.textContent = text;
    content.append(h4, p);

    const closeBtn = document.createElement('button');
    closeBtn.className = 'toast-close-btn';
    closeBtn.textContent = '×';
    closeBtn.setAttribute('aria-label', 'Dismiss');
    closeBtn.onclick = () => dismissToast(toast);

    toast.append(iconEl, content, closeBtn);
    wrapper.appendChild(toast);

    // Double rAF ensures the element is painted before the transition fires
    requestAnimationFrame(() => requestAnimationFrame(() => toast.classList.add('toast-visible')));
};