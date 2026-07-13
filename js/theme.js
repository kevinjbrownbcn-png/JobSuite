// Shared dark/light theme switcher — used by every HTML surface (launcher, hunter,
// dashboard). Loaded synchronously and early in <head> (not as a module, not deferred)
// so the `data-theme` attribute is set before first paint and there's no flash of the
// wrong theme. Persists the choice in localStorage; defaults to dark.
(function () {
    const STORAGE_KEY = 'jobsuite_theme';

    function getStoredTheme() {
        try {
            return localStorage.getItem(STORAGE_KEY);
        } catch (e) {
            return null;
        }
    }

    function applyTheme(theme) {
        const resolved = theme === 'light' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', resolved);
        try { localStorage.setItem(STORAGE_KEY, resolved); } catch (e) { /* ignore */ }
        document.dispatchEvent(new CustomEvent('jobsuite-theme-change', { detail: { theme: resolved } }));
    }

    function currentTheme() {
        return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
    }

    function initTheme() {
        applyTheme(getStoredTheme() || 'dark');
    }

    function toggleTheme() {
        applyTheme(currentTheme() === 'light' ? 'dark' : 'light');
    }

    // Wires a button to reflect + control the current theme: sets its icon/label now,
    // updates them on every change (from this button or any other), and toggles on click.
    function bindThemeToggleButton(btn) {
        if (!btn) return;
        const sync = () => {
            const theme = currentTheme();
            btn.textContent = theme === 'light' ? '🌙 Dark' : '☀️ Light';
            btn.title = theme === 'light' ? 'Switch to dark theme' : 'Switch to light theme';
        };
        btn.addEventListener('click', toggleTheme);
        document.addEventListener('jobsuite-theme-change', sync);
        sync();
    }

    window.JobSuiteTheme = { initTheme, toggleTheme, applyTheme, currentTheme, bindThemeToggleButton };
    initTheme();
})();
