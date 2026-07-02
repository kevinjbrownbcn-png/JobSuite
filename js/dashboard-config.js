// Global System Configuration Matrix
const CONFIG = {
    // Paste your exact web app deployment URL below:
    API_URL: 'https://script.google.com/macros/s/AKfycbzdzaGptKsef67xYKWELeMwRmtDRF-uRwQLkwWSTYqnOPfo127jdszE2c8EuXZAQirnZQ/exec',
    
	INTERVIEW_KEYWORDS: ['interview', 'screen', 'assessment', 'technical', 'panel', 'l0', 'l1', 'l2'],
    OFFER_KEYWORDS: ['offer', 'hired', 'accepted'],
    STALE_DAYS_THRESHOLD: 14,
    
    // UPDATED: Points exactly to your new formula column title
    FEEDBACK_DAYS_COLUMN: 'Response Time', 
    REPLY_DATE_COLUMN: 'Date of Reply'        
};

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