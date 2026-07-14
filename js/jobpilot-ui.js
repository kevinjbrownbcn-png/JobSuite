// JobPilot Mode A (ATS Analyzer) — desktop UI. Lists matches that have a tailored CV
// ready (Processed status + cv_doc_id), lets the user run/re-run a Claude-scored ATS
// fit analysis against the job description already on that match, and shows the result.

function escapeHTML(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Same red (0%) -> yellow (50%) -> green (100%) scale used everywhere else in the app.
function scoreToColor(score) {
    if (score === null || score === undefined || score === '' || isNaN(score)) return 'var(--text-muted)';
    const pct = Math.max(0, Math.min(100, Number(score))) / 100;
    return `hsl(${pct * 120}, 70%, 45%)`;
}

function dismissToast(toast) {
    toast.classList.remove('toast-visible');
    toast.classList.add('toast-hiding');
    setTimeout(() => toast.remove(), 320);
}

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
    requestAnimationFrame(() => requestAnimationFrame(() => toast.classList.add('toast-visible')));
};

function pillList(items, colorVar) {
    if (!items || items.length === 0) return '<span style="color: var(--text-muted); font-size: 12px;">None</span>';
    return items.map(s => `<span class="badge-gap" style="color: ${colorVar};">${escapeHTML(s)}</span>`).join('');
}

function subscoreRow(label, value) {
    // Every subscore is "higher is better" except Format Risk, where higher is worse —
    // invert it before feeding the shared red/green scale so the color still reads
    // correctly (high risk = red, not green).
    const colorValue = (label === 'Format Risk' && value !== null && value !== undefined) ? 100 - value : value;
    return `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 0;">
            <span style="font-size: 12px; color: var(--text-muted);">${escapeHTML(label)}</span>
            <span style="font-size: 13px; font-weight: 700; color: ${scoreToColor(colorValue)};">${value ?? '—'}</span>
        </div>`;
}

function renderResultsPanel(session) {
    const div = document.createElement('div');
    div.style.cssText = 'padding: 16px; background: var(--nav-underlay); border-radius: 10px; margin-top: 10px;';

    div.innerHTML = `
        <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 14px;">
            <div style="text-align: center;">
                <div style="font-size: 32px; font-weight: 800; color: ${scoreToColor(session.overall_score)};">${session.overall_score ?? '—'}</div>
                <div style="font-size: 10px; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.05em;">Overall Fit</div>
            </div>
            <div style="flex: 1; display: grid; grid-template-columns: 1fr 1fr; gap: 0 24px;">
                ${subscoreRow('Skills Match', session.skills_match)}
                ${subscoreRow('Seniority Match', session.seniority_match)}
                ${subscoreRow('Domain Match', session.domain_match)}
                ${subscoreRow('Experience Match', session.experience_match)}
                ${subscoreRow('Format Risk', session.format_risk)}
            </div>
        </div>
        <details style="margin-bottom: 12px;">
            <summary style="cursor: pointer; font-size: 11px; color: var(--text-muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">ⓘ What do these scores mean?</summary>
            <div style="margin-top: 8px; font-size: 12px; color: var(--text-muted); line-height: 1.6;">
                <p style="margin: 0 0 6px 0;"><strong style="color: var(--text-main);">Skills Match</strong> — how many of the job's explicitly-named tools/skills show up in the CV. Higher is better.</p>
                <p style="margin: 0 0 6px 0;"><strong style="color: var(--text-main);">Seniority Match</strong> — whether the CV's title/scope/years line up with the seniority the role expects. Higher is better.</p>
                <p style="margin: 0 0 6px 0;"><strong style="color: var(--text-main);">Domain Match</strong> — how closely the candidate's industry/domain background aligns with this role's field. Higher is better.</p>
                <p style="margin: 0 0 6px 0;"><strong style="color: var(--text-main);">Experience Match</strong> — how well the depth and relevance of past roles fits what's being asked. Higher is better.</p>
                <p style="margin: 0 0 6px 0;"><strong style="color: var(--text-main);">Format Risk</strong> — the odd one out: <em>higher means worse</em>. Flags things like missing contact info or a structure that could trip up ATS parsing or a human skim-read.</p>
                <p style="margin: 0;"><strong style="color: var(--text-main);">Overall Fit</strong> — a fixed weighted formula, not a separate judgment call: 30% Skills + 20% Seniority + 20% Domain + 15% Experience + 15% (100 − Format Risk). Same weighting every time, so scores are comparable across applications.</p>
            </div>
        </details>
        <p style="font-size: 13px; color: var(--text-main); margin: 0 0 12px 0; line-height: 1.5;">${escapeHTML(session.summary || '')}</p>
        <div class="job-details-grid" style="border-top: 1px solid var(--border); padding-top: 12px;">
            <div class="details-col">
                <h5>Matched Skills</h5>
                <div class="pill-wrapper">${pillList(session.matched_skills, '#34d399')}</div>
            </div>
            <div class="details-col">
                <h5>Missing Skills</h5>
                <div class="pill-wrapper">${pillList(session.missing_skills, '#f87171')}</div>
            </div>
        </div>
        <div class="job-details-grid" style="border-top: none; padding-top: 12px;">
            <div class="details-col">
                <h5>Missing Evidence</h5>
                <ul class="resource-items">${(session.missing_evidence || []).map(s => `<li>${escapeHTML(s)}</li>`).join('') || '<li style="color: var(--text-muted);">None noted</li>'}</ul>
            </div>
            <div class="details-col">
                <h5>Risks</h5>
                <ul class="resource-items">${(session.risks || []).map(s => `<li>${escapeHTML(s)}</li>`).join('') || '<li style="color: var(--text-muted);">None noted</li>'}</ul>
            </div>
        </div>
        <div class="details-col" style="margin-top: 12px;">
            <h5>Recommendations</h5>
            <ul class="resource-items">${(session.recommendations || []).map(s => `<li>${escapeHTML(s)}</li>`).join('') || '<li style="color: var(--text-muted);">None noted</li>'}</ul>
        </div>
    `;
    return div;
}

async function runAnalysis(matchId, btn, row) {
    const loader = document.getElementById('loading-state');
    if (loader) loader.classList.remove('hidden');
    if (btn) { btn.disabled = true; btn.textContent = 'Analyzing…'; }

    try {
        const response = await fetch('/api/prep-sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ match_id: matchId }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);

        document.querySelectorAll('.jobpilot-results-row').forEach(el => el.remove());
        const resultsRow = document.createElement('tr');
        resultsRow.className = 'jobpilot-results-row';
        const td = document.createElement('td');
        td.colSpan = 4;
        td.appendChild(renderResultsPanel(data));
        resultsRow.appendChild(td);
        row.after(resultsRow);

        window.showAlert('Analysis Complete', `Overall fit score: ${data.overall_score}%`, 'success');
    } catch (err) {
        window.showAlert('Analysis Failed', err.message, 'error');
    } finally {
        if (loader) loader.classList.add('hidden');
        if (btn) { btn.disabled = false; btn.textContent = 'Run ATS Analysis'; }
    }
}

export async function renderEligibleMatches() {
    const tbody = document.getElementById('jobpilot-matches-tbody');
    const emptyState = document.getElementById('jobpilot-empty');
    if (!tbody) return;

    let matches = [];
    try {
        const response = await fetch('/api/prep-sessions/eligible');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        matches = await response.json();
    } catch (err) {
        console.error('Failed to load eligible matches:', err);
        window.showAlert('Load Failed', `Could not load eligible matches: ${err.message}`, 'error');
        return;
    }

    tbody.innerHTML = '';

    if (!matches || matches.length === 0) {
        if (emptyState) emptyState.classList.remove('hidden');
        return;
    }
    if (emptyState) emptyState.classList.add('hidden');

    matches.forEach(match => {
        const row = document.createElement('tr');

        const tdTitle = document.createElement('td');
        tdTitle.innerHTML = `<span style="font-weight:600; color:var(--text-main);">${escapeHTML(match.job_title)}</span><br><span style="color:var(--text-muted); font-size:11px;">${escapeHTML(match.company)}</span>`;

        const tdCv = document.createElement('td');
        if (match.cv_doc_url) {
            tdCv.innerHTML = `<a href="${escapeHTML(match.cv_doc_url)}" target="_blank" style="color:#38bdf8; text-decoration:none; font-size:11px;">Tailored CV ↗</a>`;
        } else {
            tdCv.innerHTML = '<span style="color:var(--text-muted); font-size:11px;">—</span>';
        }

        const tdScore = document.createElement('td');
        tdScore.style.textAlign = 'center';
        tdScore.textContent = '—';

        const tdAction = document.createElement('td');
        tdAction.style.textAlign = 'right';
        const btn = document.createElement('button');
        btn.className = 'btn-export';
        btn.textContent = 'Run ATS Analysis';
        btn.onclick = () => runAnalysis(match.id, btn, row);
        tdAction.appendChild(btn);

        row.append(tdTitle, tdCv, tdScore, tdAction);
        tbody.appendChild(row);

        // Show the latest existing session, if any, without requiring a re-run.
        fetch(`/api/prep-sessions?match_id=${match.id}`)
            .then(r => r.ok ? r.json() : [])
            .then(sessions => {
                if (sessions && sessions.length > 0) {
                    tdScore.innerHTML = `<span style="color:${scoreToColor(sessions[0].overall_score)}; font-weight:bold;">${sessions[0].overall_score}%</span>`;
                }
            })
            .catch(() => {});
    });
}
