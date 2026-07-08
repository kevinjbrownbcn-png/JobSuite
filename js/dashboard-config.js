// Global System Configuration Matrix
const CONFIG = {
    // Local backend — replaces the old Google Apps Script Web App URL.
    API_URL: '/api/applications',

	INTERVIEW_KEYWORDS: ['interview', 'screen', 'assessment', 'technical', 'panel', 'l0', 'l1', 'l2'],
    OFFER_KEYWORDS: ['offer', 'hired', 'accepted'],
    STALE_DAYS_THRESHOLD: 14,

    // UPDATED: Points exactly to your new formula column title
    FEEDBACK_DAYS_COLUMN: 'Response Time',
    REPLY_DATE_COLUMN: 'Date of Reply',

    // Canonical status list for the editable Status dropdown in the Applications Viewer —
    // matches the real primary Tracker sheet's status progression exactly.
    APPLICATION_STATUSES: [
        'Application Sent', 'Application Received', 'Application under Review',
        'Follow-up', 'Interview Arranged', 'Interview held', 'Offer made',
        'Offer Accepted', 'Application Declined', 'Not moving forward after interview',
        'Radio Silence'
    ],

    // Sentiment-based coloring for the Status dropdown: blue/neutral early on, amber
    // while pending action, purple once interviewing, green for good outcomes, red for
    // rejections, gray for stale. Falls back to STATUS_COLOR_FALLBACK for anything else
    // (e.g. legacy values from seeded data not in the canonical list above).
    STATUS_COLORS: {
        'Application Sent': '#60a5fa',
        'Application Received': '#38bdf8',
        'Application under Review': '#fbbf24',
        'Follow-up': '#fb923c',
        'Interview Arranged': '#c084fc',
        'Interview held': '#a855f7',
        'Offer made': '#4ade80',
        'Offer Accepted': '#22c55e',
        'Application Declined': '#f87171',
        'Not moving forward after interview': '#ef4444',
        'Radio Silence': '#6b7280'
    },
    STATUS_COLOR_FALLBACK: '#9ca3af',

    // Fixed colors for the known Category values (mirrors hunter-profiles.json's
    // "profiles" list). CATEGORY_COLOR_PALETTE is a rotating fallback for anything new.
    CATEGORY_COLORS: {
        'Localization': '#2dd4bf',
        'Data Analysis': '#818cf8',
        'Tech Support': '#fb7185'
    },
    CATEGORY_COLOR_PALETTE: ['#f472b6', '#facc15', '#34d399', '#60a5fa', '#fb923c', '#a78bfa']
};

// Deterministic fallback color for a Category (or anything else) not in a fixed map —
// same string always picks the same palette entry, so colors stay stable across reloads.
function colorForKey(key, fixedMap, palette, fallback) {
    if (fixedMap[key]) return fixedMap[key];
    if (!key) return fallback;
    let hash = 0;
    for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
    return palette[hash % palette.length];
}

// Global application state tracker
let AppState = {
    rawLengthData: [],
    processedData: [],     
    sortKey: 'Date Applied',
    sortAscending: false,
    activeStatusFilter: 'ALL',
    charts: {
        status: null,
        channel: null,
        role: null,
        feedback: null 
	}
};