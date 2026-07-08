async function fetchDashboardData() {
    document.getElementById('loading').classList.remove('hidden');
    document.getElementById('tab-metrics').classList.add('hidden');
    document.getElementById('tab-data').classList.add('hidden');
    
    try {
        const response = await fetch(CONFIG.API_URL, {
            method: 'GET',
            mode: 'cors',
            redirect: 'follow'
        });
        
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        
        // Reverse array so new entries default to top priority processing
        AppState.rawLengthData = data.reverse();
        
        processAndRenderAll();
        document.getElementById('loading').classList.add('hidden');
        switchTab('metrics');
        
    } catch (error) {
        console.error("API Gateway Connection Error:", error);
        document.getElementById('loading').innerHTML = `
            <p class="text-red-400 font-semibold">Failed to connect to data stream.</p>
            <p class="text-xs text-gray-500 mt-2 max-w-md mx-auto">Error details: ${error.message}<br>Check file injection parameters inside js/config.js.</p>
        `;
    }
}

const MONTH_MAP = {
    jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
    jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11
};

function parseDate(dateString) {
    if (!dateString) return null;
    const dateStr = String(dateString).trim();
    const textMonthMatch = dateStr.match(/^(\d{1,2})[\/\-]([A-Za-z]{3})[\/\-](\d{4})/);
    if (textMonthMatch) {
        const month = MONTH_MAP[textMonthMatch[2].toLowerCase()];
        return new Date(parseInt(textMonthMatch[3], 10), month !== undefined ? month : 0, parseInt(textMonthMatch[1], 10));
    }
    const nativeDate = new Date(dateStr);
    return isNaN(nativeDate.getTime()) ? null : nativeDate;
}

function calculateDaysSince(dateString) {
    if (!dateString || dateString === '—' || dateString === 'N/A') return null;
    const appliedDate = parseDate(dateString);
    if (!appliedDate) return null;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    appliedDate.setHours(0, 0, 0, 0);
    return Math.floor((today.getTime() - appliedDate.getTime()) / (1000 * 3600 * 24));
}

function convertToComparableDate(dateString) {
    return parseDate(dateString) ?? new Date(0);
}

// Persists a single field edit (Status, Notes) back to the local API and updates
// the in-memory copy so the table/KPIs stay in sync without a full refetch.
async function updateApplicationField(id, field, value) {
    try {
        const response = await fetch(`/api/applications/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ [field]: value })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error || `HTTP ${response.status}`);
        }

        const updatedRow = await response.json();
        if (updatedRow._archive_warning) {
            console.warn('[dashboard] Archive webhook warning:', updatedRow._archive_warning);
        }

        const idx = AppState.processedData.findIndex(row => row._id === id);
        if (idx !== -1) {
            const age = calculateDaysSince(updatedRow['Date Applied']);
            AppState.processedData[idx] = { ...updatedRow, _calculatedAge: age === null ? -1 : age };
        }
        const rawIdx = AppState.rawLengthData.findIndex(row => row._id === id);
        if (rawIdx !== -1) AppState.rawLengthData[rawIdx] = updatedRow;

        return updatedRow;
    } catch (error) {
        console.error('Failed to update application field:', error);
        window.showAlert ? window.showAlert('Update Failed', error.message, 'error')
                          : alert(`Update failed: ${error.message}`);
        throw error;
    }
}