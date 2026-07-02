// Role mapping dictionary loaded from roles-config.json at runtime.
// ROLE_MAPPING_DICTIONARY is populated async; processAndRenderAll awaits roleDictionaryReady.
window.ROLE_MAPPING_DICTIONARY = {};

window.roleDictionaryReady = window.fetch('/roles-config.json')
    .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
    })
    .then(data => { window.ROLE_MAPPING_DICTIONARY = data; })
    .catch(err => console.warn('[roles] Could not load roles-config.json — role chart will be empty.', err));
