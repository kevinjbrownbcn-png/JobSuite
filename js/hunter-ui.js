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

// Continuous red (0%) -> yellow (50%) -> green (100%) scale, matching the color-scale
// conditional formatting the match scores used to have in the spreadsheet.
function scoreToColor(score) {
    if (score === null || score === undefined || score === '' || isNaN(score)) return 'var(--text-muted)';
    const pct = Math.max(0, Math.min(100, Number(score))) / 100;
    return `hsl(${pct * 120}, 70%, 45%)`;
}

// Workday-hosted career sites virtually always run on this domain, regardless of the
// company's own branding — good enough as an auto-detect default, with the card's
// checkbox left editable for the cases it misses (custom domains, etc).
const WORKDAY_URL_PATTERN = /myworkdayjobs\.com/i;

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

// Merges newly-audited jobs into whatever's already showing (used by the Manual Audit
// panels, which should stack up across multiple audits instead of replacing each other —
// unlike the Web Scanner, which always starts a fresh list via renderJobCards directly).
// Dedupes by title+company against what's already there so re-auditing the same posting
// doesn't produce a second card.
export function appendJobCards(newJobs) {
    const existing = Array.isArray(window.currentJobsList) ? window.currentJobsList : [];
    const existingSignatures = new Set(
        existing
            .filter(j => j.job_title && j.company)
            .map(j => `${j.job_title.toLowerCase().trim()}_${j.company.toLowerCase().trim()}`)
    );
    const toAdd = newJobs.filter(job => {
        if (!job.job_title || !job.company) return true;
        return !existingSignatures.has(`${job.job_title.toLowerCase().trim()}_${job.company.toLowerCase().trim()}`);
    });
    renderJobCards([...existing, ...toAdd]);
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

        // Auto-detect once per job (mutating it in place) so a re-render — e.g. from
        // appendJobCards stacking another audit on top — doesn't clobber a manual
        // toggle with a fresh auto-detect result.
        if (job.is_workday === undefined) {
            job.is_workday = WORKDAY_URL_PATTERN.test(job.link || job.job_url || '');
        }

        const card = document.createElement('div');
        card.className = "job-card";
        card.dataset.jobData = JSON.stringify(job);

        // Score badge coloring: continuous red -> yellow -> green scale
        const scoreColor = scoreToColor(job.match_score);

        const skillGapsHTML = Array.isArray(job.skills_gaps) && job.skills_gaps.length > 0
            ? job.skills_gaps.map(g => `<span class="badge-gap">${escapeHTML(g)}</span>`).join('')
            : `<span style="color: var(--success); font-size: 12px; font-weight: bold;">✓ Perfect Toolkit Alignment</span>`;

        const safeLink = job.link && job.link.startsWith('http') ? job.link : null;

        card.innerHTML = `
            <div class="card-left-select">
                <input type="checkbox" class="job-card-checkbox" data-index="${index}" onchange="this.closest('.job-card').classList.toggle('selected', this.checked); window.updateSelectedCounter();">
            </div>
            <div style="flex-grow: 1; display: flex; flex-direction: column; gap: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;">
                    <div>
                        <h4 class="card-title">${escapeHTML(job.job_title) || 'Inferred Position'}</h4>
                        <p class="card-subtitle">${escapeHTML(job.company) || 'Unknown Studio'} — <span style="color: var(--text-muted);">${escapeHTML(job.location) || 'Manual Text Audit'}</span></p>
                    </div>
                    <div class="card-score-badge" style="background-color: ${scoreColor};">${job.match_score || 0}% Match</div>
                </div>

                <p class="card-summary">${escapeHTML(job.summary) || ''}</p>

                <div class="gap-section">
                    <div class="gap-title">Skill Gaps Identified</div>
                    <div style="display: flex; flex-wrap: wrap; gap: 6px;">${skillGapsHTML}</div>
                </div>

                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 8px; border-top: 1px solid var(--border); padding-top: 8px;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        ${safeLink
                            ? `<a href="${escapeHTML(safeLink)}" target="_blank" class="card-link-anchor" title="${escapeHTML(safeLink)}" style="margin: 0;">Open Original Job Website ↗</a><span class="link-status-pill link-status-checking">⏳</span>`
                            : '<span></span>'}
                        ${job._reposted ? '<span class="link-status-pill link-status-repost" title="Previously discarded, reappeared in this scan">↻ Reposted</span>' : ''}
                        <label style="display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--text-muted); cursor: pointer; user-select: none;" title="Tailor the generated CV for Workday's ATS parser. Auto-detected from the job URL — override if it's wrong.">
                            <input
                                type="checkbox"
                                class="workday-ats-checkbox"
                                ${job.is_workday ? 'checked' : ''}
                                onchange="window.currentJobsList[${index}].is_workday = this.checked;"
                            >
                            Workday ATS
                        </label>
                    </div>
                    <div style="display: flex; gap: 6px;">
                        <button
                            class="single-discard-btn"
                            style="background: none; color: var(--error); border: 1px solid var(--error); padding: 4px 10px; border-radius: 4px; font-size: 11px; cursor: pointer; font-weight: 600;"
                            title="Store on the tracker for reference without acting on it — e.g. a dead/expired listing"
                            onclick="window.discardJobPosting(window.currentJobsList[${index}])"
                        >
                            Discard
                        </button>
                        <button
                            class="single-export-btn"
                            style="background: var(--panel); color: #38bdf8; border: 1px solid #38bdf8; padding: 4px 10px; border-radius: 4px; font-size: 11px; cursor: pointer; font-weight: 600;"
                            onclick="window.exportJobsToTracker(window.currentJobsList[${index}])"
                        >
                            Sync to Tracker →
                        </button>
                    </div>
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