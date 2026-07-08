import { saveParamState } from './hunter-ui.js';

async function loadHunterProfiles() {
    try {
        const response = await window.fetch('/hunter-profiles.json');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (err) {
        console.warn('[hunter-config] hunter-profiles.json not found — UI defaults unchanged.', err);
        return null;
    }
}

function buildRolesList(profiles, listContainer) {
    listContainer.innerHTML = '';
    profiles.roles.forEach(role => {
        const label = document.createElement('label');
        label.className = 'checkbox-row';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.id = role.id;
        input.value = role.value;
        input.checked = !!role.defaultChecked;
        const span = document.createElement('span');
        span.textContent = role.label;
        label.append(input, span);
        listContainer.appendChild(label);
    });
}

function buildProfileDropdowns(profiles) {
    ['manual-profile', 'direct-analysis-profile', 'hub-analysis-profile'].forEach(id => {
        const sel = document.getElementById(id);
        if (!sel) return;
        sel.innerHTML = '';
        profiles.profiles.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.value;
            opt.textContent = p.label;
            sel.appendChild(opt);
        });
    });
}

const POSTING_SOURCE_SELECT_IDS = [
    'manual-text-posting-source', 'direct-analysis-posting-source', 'hub-analysis-posting-source'
];

function buildPostingSourceDropdowns(profiles) {
    const sources = profiles.postingSources || [];
    POSTING_SOURCE_SELECT_IDS.forEach(id => {
        const sel = document.getElementById(id);
        if (!sel) return;
        sel.innerHTML = '';
        const blankOpt = document.createElement('option');
        blankOpt.value = '';
        blankOpt.textContent = '— Select —';
        sel.appendChild(blankOpt);
        sources.forEach(source => {
            const opt = document.createElement('option');
            opt.value = source;
            opt.textContent = source;
            sel.appendChild(opt);
        });
        const otherOpt = document.createElement('option');
        otherOpt.value = '__other__';
        otherOpt.textContent = 'Other...';
        sel.appendChild(otherOpt);

        const otherInput = document.getElementById(id + '-other');
        if (otherInput) {
            sel.onchange = () => {
                otherInput.classList.toggle('hidden', sel.value !== '__other__');
            };
        }
    });
}

// Adds a newly-learned source as an option on every Posting Source dropdown (before
// "Other..."), so it's immediately pickable for the rest of this session without a reload.
function addPostingSourceOption(newSource) {
    POSTING_SOURCE_SELECT_IDS.forEach(id => {
        const sel = document.getElementById(id);
        if (!sel) return;
        const alreadyPresent = Array.from(sel.options).some(o => o.value.toLowerCase() === newSource.toLowerCase());
        if (alreadyPresent) return;
        const opt = document.createElement('option');
        opt.value = newSource;
        opt.textContent = newSource;
        const otherOpt = Array.from(sel.options).find(o => o.value === '__other__');
        sel.insertBefore(opt, otherOpt || null);
    });
}

const _persistedSources = new Set(); // avoids re-POSTing the same value repeatedly in one session

// Persists a custom "Other" entry to hunter-profiles.json (via the local API) so it
// shows up in the dropdown for future sessions too — best-effort, doesn't block the caller.
function persistPostingSource(value) {
    if (!value || _persistedSources.has(value)) return;
    _persistedSources.add(value);
    fetch('/api/posting-sources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: value })
    })
        .then(() => addPostingSourceOption(value))
        .catch(err => console.warn('[hunter-config] Could not persist new posting source:', err));
}

// Reads the effective value of a Posting Source dropdown, falling back to the
// adjacent "Other" text input when that option is selected — and persisting genuinely
// new custom values so they don't need re-typing (or a code change) next time.
export function getPostingSourceValue(selectId) {
    const sel = document.getElementById(selectId);
    if (!sel) return '';
    if (sel.value === '__other__') {
        const otherInput = document.getElementById(selectId + '-other');
        const value = otherInput ? otherInput.value.trim() : '';
        if (value) persistPostingSource(value);
        return value;
    }
    return sel.value;
}

export async function loadParamState() {
    // Load profiles JSON — populates roles list and profile dropdowns
    const profiles = await loadHunterProfiles();
    const listContainer = document.getElementById('roles-checkbox-list');

    if (profiles) {
        if (listContainer) buildRolesList(profiles, listContainer);
        buildProfileDropdowns(profiles);
        buildPostingSourceDropdowns(profiles);
    }

    const savedState = localStorage.getItem('job_hunter_param_state') || localStorage.getItem('global_shared_hunter_param_state');

    if (!savedState) {
        // No prior session — apply JSON defaults for location and focus
        if (profiles) {
            const locEl = document.getElementById('search-location');
            const focEl = document.getElementById('search-focus');
            if (locEl && profiles.defaultLocation) locEl.value = profiles.defaultLocation;
            if (focEl && profiles.defaultFocus)    focEl.value = profiles.defaultFocus;
        }
        attachChangeListeners();
        return;
    }

    try {
        const state = JSON.parse(savedState);

        // Restore saved checkbox states; also re-add any custom roles from the saved session
        if (listContainer && state.roles) {
            state.roles.forEach(role => {
                let checkbox = document.getElementById(role.id);
                if (!checkbox && role.isCustom) {
                    const newLabel = document.createElement('label');
                    newLabel.className = 'checkbox-row';
                    const input = document.createElement('input');
                    input.type = 'checkbox';
                    input.id = role.id;
                    input.value = role.value;
                    const span = document.createElement('span');
                    span.textContent = role.value;
                    newLabel.append(input, span);
                    listContainer.appendChild(newLabel);
                    checkbox = document.getElementById(role.id);
                }
                if (checkbox) checkbox.checked = role.checked;
            });
        }

        const locEl  = document.getElementById('search-location');
        const timeEl = document.getElementById('search-time');
        const focEl  = document.getElementById('search-focus');
        if (state.location && locEl)  locEl.value  = state.location;
        if (state.time    && timeEl)  timeEl.value = state.time;
        if (state.focus   && focEl)   focEl.value  = state.focus;
    } catch (e) {
        console.warn("State synchronization bypassed safely.");
    }

    attachChangeListeners();
}

function attachChangeListeners() {
    document.querySelectorAll('#roles-checkbox-list input[type="checkbox"]').forEach(el => {
        el.onchange = saveParamState;
    });
    const loc = document.getElementById('search-location');
    const tm  = document.getElementById('search-time');
    const foc = document.getElementById('search-focus');
    if (loc) loc.oninput  = saveParamState;
    if (tm)  tm.onchange  = saveParamState;
    if (foc) foc.oninput  = saveParamState;
}
