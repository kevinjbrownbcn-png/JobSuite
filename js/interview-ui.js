// JobPilot Mode B (Interview Assistant) — desktop UI. Lists any match with a job
// description, lets the user start/resume/re-run a persona-specific mock interview,
// and renders the turn-by-turn Q&A as a "support chatbot"-style chat panel.

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

// Colors drawn from Kevin's standard accent set — each persona gets a stable, distinct one.
const PERSONAS = {
    recruiter: { label: 'Recruiter / HR', icon: '🧑‍💼', color: '#eab308' },
    hiring_manager: { label: 'Hiring Manager', icon: '👔', color: '#2dd4bf' },
    department_manager: { label: 'Department Manager', icon: '📈', color: '#a855f7' },
    peer: { label: 'Peer Interviewer', icon: '🤝', color: '#10b981' },
};

let activeButton = null;

function collapsePanel() {
    document.querySelectorAll('.interview-panel-row').forEach(el => el.remove());
    if (activeButton) activeButton.style.filter = '';
    activeButton = null;
}

function questionBubble(text, personaCfg) {
    return `
        <div style="display:flex; gap:10px; margin-bottom: 10px; align-items:flex-start;">
            <div style="width:28px; height:28px; border-radius:50%; background:${personaCfg.color}22; border:1px solid ${personaCfg.color}66; display:flex; align-items:center; justify-content:center; font-size:14px; flex-shrink:0;">${personaCfg.icon}</div>
            <div style="background:var(--panel); border:1px solid var(--border); border-radius: 4px 14px 14px 14px; padding:10px 14px; max-width:80%; font-size:13px; color:var(--text-main); line-height:1.5;">${escapeHTML(text)}</div>
        </div>`;
}

function answerBubble(text) {
    return `
        <div style="display:flex; justify-content:flex-end; margin-bottom: 4px;">
            <div style="background:var(--accent); color:#0b0f19; border-radius:14px 4px 14px 14px; padding:10px 14px; max-width:80%; font-size:13px; line-height:1.5; font-weight:500;">${escapeHTML(text)}</div>
        </div>`;
}

function feedbackBlock(turn) {
    if (turn.answer_score === null || turn.answer_score === undefined) return '';
    return `
        <div style="margin: 4px 0 16px 38px; font-size: 12px; color: var(--text-muted);">
            <span style="font-weight:700; color:${scoreToColor(turn.answer_score)};">${turn.answer_score}%</span>
            ${(turn.feedback || []).map(f => `<div style="margin-top:2px;">• ${escapeHTML(f)}</div>`).join('')}
            <div style="margin-top:6px; display:flex; gap:6px; flex-wrap:wrap;">
                ${(turn.strengths || []).map(s => `<span class="badge-gap" style="color:#34d399;">${escapeHTML(s)}</span>`).join('')}
                ${(turn.gaps || []).map(s => `<span class="badge-gap" style="color:#f87171;">${escapeHTML(s)}</span>`).join('')}
            </div>
        </div>`;
}

// `onUpdate(session)` is called by the submit/restart handlers below with the fresh
// session state — the caller (openPersona) owns re-rendering into the right <td>.
function renderChatPanel(session, matchId, persona, onUpdate) {
    const personaCfg = PERSONAS[persona];
    const div = document.createElement('div');
    div.style.cssText = 'padding: 16px; background: var(--nav-underlay); border-radius: 10px; margin-top: 10px; max-width: 720px;';

    let html = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:18px;">${personaCfg.icon}</span>
                <span style="font-weight:700; color:${personaCfg.color};">${personaCfg.label}</span>
                <span style="font-size:11px; padding:2px 8px; border-radius:999px; background:var(--panel); color:var(--text-muted); border:1px solid var(--border);">${session.status === 'completed' ? 'Completed' : 'In progress'}</span>
            </div>
        </div>`;

    if (!session.resume_structured) {
        html += `<div style="font-size:11px; color:var(--text-muted); background:var(--panel); border:1px solid var(--border); border-radius:6px; padding:8px 12px; margin-bottom:12px;">ⓘ No CV data available for this posting — questions are based on the job description only.</div>`;
    }

    (session.turns || []).forEach(turn => {
        html += questionBubble(turn.question, personaCfg);
        if (turn.answer) {
            html += answerBubble(turn.answer);
            html += feedbackBlock(turn);
        }
    });

    if (session.status === 'completed') {
        html += `
            <div style="border-top:1px solid var(--border); padding-top:12px; margin-top:4px; display:flex; align-items:center; gap:10px;">
                <div style="font-size:24px; font-weight:800; color:${scoreToColor(session.overall_score)};">${session.overall_score ?? '—'}%</div>
                <div style="font-size:11px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.05em;">Session Score</div>
            </div>`;
    }

    div.innerHTML = html;

    if (session.status !== 'completed') {
        const inputWrap = document.createElement('div');
        inputWrap.style.cssText = 'display:flex; flex-direction:column; gap:8px; margin-top: 8px;';
        const textarea = document.createElement('textarea');
        textarea.placeholder = 'Type your answer…';
        textarea.rows = 3;
        textarea.style.cssText = 'width:100%; background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:10px 12px; color:var(--text-main); font-size:13px; font-family:inherit; resize:vertical;';
        const submitBtn = document.createElement('button');
        submitBtn.className = 'btn-export';
        submitBtn.textContent = 'Submit Answer';
        submitBtn.style.alignSelf = 'flex-end';
        submitBtn.onclick = () => submitAnswer(session, onUpdate, submitBtn, textarea);
        inputWrap.append(textarea, submitBtn);
        div.appendChild(inputWrap);
    } else {
        const restartWrap = document.createElement('div');
        restartWrap.style.cssText = 'margin-top: 12px; text-align: right;';
        const restartBtn = document.createElement('button');
        restartBtn.className = 'btn-export';
        restartBtn.textContent = 'Start New Session';
        restartBtn.onclick = () => startFreshSession(matchId, persona, onUpdate);
        restartWrap.appendChild(restartBtn);
        div.appendChild(restartWrap);
    }

    return div;
}

async function submitAnswer(session, onUpdate, submitBtn, textarea) {
    const answer = textarea.value.trim();
    if (!answer) return;
    submitBtn.disabled = true;
    textarea.disabled = true;
    submitBtn.textContent = 'Scoring…';

    try {
        const response = await fetch(`/api/interview-sessions/${session.id}/turn`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ answer }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
        onUpdate(data);
    } catch (err) {
        window.showAlert('Submit Failed', err.message, 'error');
        submitBtn.disabled = false;
        textarea.disabled = false;
        submitBtn.textContent = 'Submit Answer';
    }
}

async function startFreshSession(matchId, persona, onUpdate) {
    try {
        const response = await fetch('/api/interview-sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ match_id: matchId, persona }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
        onUpdate(data);
    } catch (err) {
        window.showAlert('Interview Failed', err.message, 'error');
    }
}

async function fetchLatestSession(matchId, persona) {
    try {
        const response = await fetch(`/api/interview-sessions?match_id=${matchId}`);
        if (!response.ok) return null;
        const sessions = await response.json();
        return sessions.find(s => s.persona === persona) || null;
    } catch (err) {
        return null;
    }
}

async function openPersona(matchId, persona, btn, row) {
    if (activeButton === btn) {
        collapsePanel();
        return;
    }
    collapsePanel();
    activeButton = btn;
    btn.style.filter = 'brightness(1.3)';

    const panelRow = document.createElement('tr');
    panelRow.className = 'interview-panel-row';
    const td = document.createElement('td');
    td.colSpan = 3;
    td.innerHTML = '<div class="loader-spinner" style="margin: 20px auto;"></div>';
    panelRow.appendChild(td);
    row.after(panelRow);

    const update = (session) => {
        td.innerHTML = '';
        td.appendChild(renderChatPanel(session, matchId, persona, update));
        refreshPersonaBadges(matchId, row);
    };

    try {
        const existing = await fetchLatestSession(matchId, persona);
        let session;
        if (existing) {
            const response = await fetch(`/api/interview-sessions/${existing.id}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            session = await response.json();
        } else {
            const response = await fetch('/api/interview-sessions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ match_id: matchId, persona }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
            session = data;
        }
        update(session);
    } catch (err) {
        window.showAlert('Interview Failed', err.message, 'error');
        panelRow.remove();
        collapsePanel();
    }
}

function applySessionBadges(row, sessions) {
    const buttons = row.__personaButtons;
    if (!buttons) return;
    Object.keys(PERSONAS).forEach(persona => {
        const btn = buttons[persona];
        const badge = btn.querySelector('.persona-badge');
        const latest = sessions.find(s => s.persona === persona);
        if (!latest) {
            badge.textContent = '';
            return;
        }
        if (latest.status === 'completed') {
            badge.textContent = `${latest.overall_score}%`;
            badge.style.color = scoreToColor(latest.overall_score);
        } else {
            badge.textContent = '● in progress';
            badge.style.color = 'var(--text-muted)';
        }
    });
}

async function refreshPersonaBadges(matchId, row) {
    try {
        const response = await fetch(`/api/interview-sessions?match_id=${matchId}`);
        if (!response.ok) return;
        const sessions = await response.json();
        applySessionBadges(row, sessions);
    } catch (err) {
        // non-fatal — badges just stay blank
    }
}

export async function renderEligibleMatches() {
    const tbody = document.getElementById('interview-matches-tbody');
    const emptyState = document.getElementById('interview-empty');
    if (!tbody) return;

    let matches = [];
    try {
        const response = await fetch('/api/interview-sessions/eligible');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        matches = await response.json();
    } catch (err) {
        console.error('Failed to load eligible matches:', err);
        window.showAlert('Load Failed', `Could not load eligible matches: ${err.message}`, 'error');
        return;
    }

    tbody.innerHTML = '';
    collapsePanel();

    if (!matches || matches.length === 0) {
        if (emptyState) emptyState.classList.remove('hidden');
        return;
    }
    if (emptyState) emptyState.classList.add('hidden');

    matches.forEach(match => {
        const row = document.createElement('tr');

        const tdTitle = document.createElement('td');
        tdTitle.innerHTML = `<span style="font-weight:600; color:var(--text-main);">${escapeHTML(match.job_title)}</span><br><span style="color:var(--text-muted); font-size:11px;">${escapeHTML(match.company)}</span>`;

        const tdData = document.createElement('td');
        const hasCv = !!match.cv_doc_id;
        tdData.innerHTML = `<span style="font-size:11px; color:var(--text-muted);">${hasCv ? 'JD + Tailored CV' : 'JD only'}</span>`;

        const tdPersonas = document.createElement('td');
        tdPersonas.style.cssText = 'display:flex; flex-wrap:wrap; gap:6px;';
        row.__personaButtons = {};
        Object.entries(PERSONAS).forEach(([persona, cfg]) => {
            const btn = document.createElement('button');
            btn.className = 'btn-export';
            btn.style.cssText = `background: transparent; border: 1px solid ${cfg.color}66; color: ${cfg.color}; display:flex; flex-direction:column; align-items:center; gap:2px; padding: 6px 10px; line-height:1.3;`;
            btn.innerHTML = `<span>${cfg.icon} ${cfg.label}</span><span class="persona-badge" style="font-size:10px; font-weight:700;"></span>`;
            btn.onclick = () => openPersona(match.id, persona, btn, row);
            row.__personaButtons[persona] = btn;
            tdPersonas.appendChild(btn);
        });

        row.append(tdTitle, tdData, tdPersonas);
        tbody.appendChild(row);

        refreshPersonaBadges(match.id, row);
    });
}
