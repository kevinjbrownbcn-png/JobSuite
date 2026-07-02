import { saveParamState } from './hunter-ui.js';

export let currentApiKey = "";

export async function getApiKeyFromConfig() {
    try {
        const response = await window.fetch('/config.json');
        if (!response.ok) throw new Error("Could not read root config file properties.");
        const configData = await response.json();
        return configData.gemini_api_key || localStorage.getItem('gemini_api_key') || '';
    } catch (error) {
        console.warn("Config file bypass. Using local storage container fallback:", error);
        return localStorage.getItem('gemini_api_key') || '';
    }
}

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

export async function loadParamState() {
    const cachedGDrive = localStorage.getItem('gdrive_webhook') || '';
    const cachedExport = localStorage.getItem('export_webhook') || '';

    const gdriveInput = document.getElementById('gdrive_webhook');
    const exportInput = document.getElementById('export_webhook');
    if (gdriveInput) gdriveInput.value = cachedGDrive;
    if (exportInput) exportInput.value = cachedExport;

    const saveBtn = document.getElementById('save-sync-routes-btn');
    if (saveBtn) {
        saveBtn.onclick = function() {
            const newGDrive = document.getElementById('gdrive_webhook').value.trim();
            const newExport = document.getElementById('export_webhook').value.trim();
            localStorage.setItem('gdrive_webhook', newGDrive);
            localStorage.setItem('export_webhook', newExport);
            window.showAlert('Route Configured', 'All Webhook pipeline routing configurations saved successfully.', 'success');
        };
    }

    // Load profiles JSON — populates roles list and profile dropdowns
    const profiles = await loadHunterProfiles();
    const listContainer = document.getElementById('roles-checkbox-list');

    if (profiles) {
        if (listContainer) buildRolesList(profiles, listContainer);
        buildProfileDropdowns(profiles);
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

export async function fetchBaseCVText(hookUrl, loadingState) {
    document.getElementById('loader-title').textContent = "Accessing Google Drive...";
    document.getElementById('loader-desc').textContent = "Downloading your base resume mapping file securely via Make.com webhook bridge.";
    loadingState.classList.remove('hidden');

    const gdriveResponse = await window.fetch(hookUrl, { method: 'POST' });
    if (!gdriveResponse.ok) throw new Error("Could not pull file text from Drive Webhook.");
    return await gdriveResponse.text();
}
