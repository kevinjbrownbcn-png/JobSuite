function renderCharts(statusCounts, channelCounts, roleCounts) {
    // Clear out active layout structures
    if(AppState.charts.status) AppState.charts.status.destroy();
    if(AppState.charts.channel) AppState.charts.channel.destroy();
    if(AppState.charts.role) AppState.charts.role.destroy();
    if(AppState.charts.feedback) AppState.charts.feedback.destroy();

    // 1. Application Funnel Chart
    const ctxStatus = document.getElementById('statusChart').getContext('2d');
    AppState.charts.status = new Chart(ctxStatus, {
        type: 'doughnut',
        data: {
            labels: Object.keys(statusCounts),
            datasets: [{ data: Object.values(statusCounts), backgroundColor: ['#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ef4444', '#6b7280'], borderWidth: 0 }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { color: '#c9d1d9', boxWidth: 10, font: { size: 9 } } } } }
    });

    // 2. Top Channels Chart
    const ctxChannel = document.getElementById('channelChart').getContext('2d');
    AppState.charts.channel = new Chart(ctxChannel, {
        type: 'bar',
        data: {
            labels: Object.keys(channelCounts),
            datasets: [{ data: Object.values(channelCounts), backgroundColor: '#3b82f6', borderRadius: 4 }]
        },
        options: { 
            responsive: true, maintainAspectRatio: false,
            scales: { y: { ticks: { color: '#c9d1d9', stepSize: 1, font: { size: 9 } }, grid: { color: '#21262d' } }, x: { ticks: { color: '#c9d1d9', font: { size: 9 } }, grid: { display: false } } },
            plugins: { legend: { display: false } }
        }
    });

    // 3. Standardized Role Types Chart (Using your expanded 6-color unique palette)
    const ctxRole = document.getElementById('roleChart').getContext('2d');
    AppState.charts.role = new Chart(ctxRole, {
        type: 'doughnut',
        data: {
            labels: Object.keys(roleCounts),
            datasets: [{ 
                data: Object.values(roleCounts), 
                backgroundColor: ['#a855f7', '#ec4899', '#f43f5e', '#6366f1', '#06b6d4', '#4b5563'], 
                borderWidth: 0 
            }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { color: '#c9d1d9', boxWidth: 10, font: { size: 9 } } } } }
    });
}

function renderSourceTable(sourceCounts) {
    const tableBody = document.getElementById('source-table-body');
    tableBody.innerHTML = '';
    const sortedSources = Object.entries(sourceCounts).sort((a, b) => b[1] - a[1]);
    sortedSources.forEach(([sourceName, count]) => {
        const tr = document.createElement('tr');
        tr.className = "border-b border-[#21262d] last:border-0 hover:bg-[#1f242c]";

        const tdName = document.createElement('td');
        tdName.className = "py-2.5 font-medium text-white";
        tdName.textContent = sourceName;

        const tdCount = document.createElement('td');
        tdCount.className = "py-2.5 text-right font-semibold text-purple-400";
        tdCount.textContent = count;

        tr.append(tdName, tdCount);
        tableBody.appendChild(tr);
    });
}