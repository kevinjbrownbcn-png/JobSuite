function addOptions(selectEl, values) {
    values.forEach(val => {
        const opt = document.createElement('option');
        opt.value = val;
        opt.textContent = val;
        selectEl.appendChild(opt);
    });
}

function populateDropdownFilters(categories, statuses, sources) {
    const catSelect = document.getElementById('filter-category');
    const statSelect = document.getElementById('filter-status');
    const srcSelect = document.getElementById('filter-source');

    catSelect.innerHTML = '<option value="ALL">All Categories</option>';
    statSelect.innerHTML = '<option value="ALL">All Statuses</option>';
    srcSelect.innerHTML = '<option value="ALL">All Posting Sources</option>';

    addOptions(catSelect, Object.keys(categories).sort());
    addOptions(statSelect, Object.keys(statuses).sort());
    addOptions(srcSelect, Object.keys(sources).sort());
}

function handleSort(key) {
    if (AppState.sortKey === key) {
        AppState.sortAscending = !AppState.sortAscending;
    } else {
        AppState.sortKey = key;
        AppState.sortAscending = true;
    }
    updateSortIcons();
    filterAndRenderDataView();
}

function updateSortIcons() {
    const icons = {
        'Date Applied': 'sort-icon-date',
        'Last Status Update': 'sort-icon-age', // Tied safely to your updated interface header slot
        'Job Title': 'sort-icon-role',
        'Category': 'sort-icon-category',
        'Status': 'sort-icon-status',
        'Posting source': 'sort-icon-source'
    };
    
    Object.values(icons).forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerText = '↕';
    });
    const activeId = icons[AppState.sortKey];
    if (activeId && document.getElementById(activeId)) {
        document.getElementById(activeId).innerText = AppState.sortAscending ? '▲' : '▼';
    }
}

function filterAndRenderDataView() {
    const searchQuery = document.getElementById('table-search').value.toLowerCase();
    const selectedCat = document.getElementById('filter-category').value;
    const selectedStat = document.getElementById('filter-status').value;
    const selectedSrc = document.getElementById('filter-source').value;
    
    const tableBody = document.getElementById('master-table-body');
    tableBody.innerHTML = '';

    let filtered = AppState.processedData.filter(row => {
        const status = (row["Status"] || "Applied").trim();
        const category = (row["Category"] || "General").trim();
        const source = (row["Posting source"] || "Direct/Other").trim();
        
        const matchesCat = (selectedCat === 'ALL' || category === selectedCat);
        const matchesStat = (selectedStat === 'ALL' || status === selectedStat);
        const matchesSrc = (selectedSrc === 'ALL' || source === selectedSrc);
        
        const matchesSearch = (row["Job Title"] || '').toLowerCase().includes(searchQuery) || 
                              (row["Company"] || '').toLowerCase().includes(searchQuery) || 
                              (row["Notes"] || '').toLowerCase().includes(searchQuery);

        return matchesCat && matchesStat && matchesSrc && matchesSearch;
    });

    filtered.sort((a, b) => {
        let valA = a[AppState.sortKey];
        let valB = b[AppState.sortKey];

        if (AppState.sortKey === 'Date Applied' || AppState.sortKey === 'Last Status Update') {
            return AppState.sortAscending 
                ? convertToComparableDate(valA) - convertToComparableDate(valB)
                : convertToComparableDate(valB) - convertToComparableDate(valA);
        }

        if (typeof valA === 'string') valA = valA.toLowerCase();
        if (typeof valB === 'string') valB = valB.toLowerCase();

        if (valA < valB) return AppState.sortAscending ? -1 : 1;
        if (valA > valB) return AppState.sortAscending ? 1 : -1;
        return 0;
    });

    document.getElementById('view-records-count').innerText = filtered.length;

    filtered.forEach(row => {
        const status = (row["Status"] || "Applied").trim();
        const jobTitle = row["Job Title"] || '';
        const company = row["Company"] || '';
        const category = (row["Category"] || 'General').trim();
        const source = (row["Posting source"] || '—').trim();
        const channel = (row["Applied Through"] || '—').trim();
        const notes = row["Notes"] || '';
        const lastUpdate = row["Last Status Update"] || '—';
        const replyDate = row["First Response Date"] || '—';
        const dateApplied = row["Date Applied"] || '—';
        const jobUrl = row["Job URL"] ? row["Job URL"].trim() : '';

        const tr = document.createElement('tr');
        tr.className = "border-b border-[#21262d] hover:bg-[#1f242c] transition-colors text-xs";

        // Date Applied cell
        const tdDate = document.createElement('td');
        tdDate.className = "py-3 font-mono text-gray-400";
        tdDate.textContent = dateApplied;
        const repliedSpan = document.createElement('span');
        repliedSpan.className = "text-[10px] text-gray-500";
        repliedSpan.textContent = `Replied: ${replyDate}`;
        tdDate.appendChild(document.createElement('br'));
        tdDate.appendChild(repliedSpan);

        // Last Status Update cell
        const tdUpdate = document.createElement('td');
        tdUpdate.className = "py-3 text-gray-300 font-mono";
        tdUpdate.textContent = lastUpdate;

        // Title + Company cell
        const tdTitle = document.createElement('td');
        tdTitle.className = "py-3";
        if (jobUrl) {
            const a = document.createElement('a');
            a.href = jobUrl;
            a.target = '_blank';
            a.className = "text-emerald-400 hover:underline font-semibold";
            a.textContent = jobTitle;
            tdTitle.appendChild(a);
            tdTitle.appendChild(document.createTextNode(' 🔗'));
        } else {
            const span = document.createElement('span');
            span.className = "text-white font-semibold";
            span.textContent = jobTitle;
            tdTitle.appendChild(span);
        }
        tdTitle.appendChild(document.createElement('br'));
        const companySpan = document.createElement('span');
        companySpan.className = "text-gray-400 text-[11px]";
        companySpan.textContent = company;
        tdTitle.appendChild(companySpan);

        // Category cell
        const tdCat = document.createElement('td');
        tdCat.className = "py-3";
        const catSpan = document.createElement('span');
        catSpan.className = "px-2 py-0.5 rounded bg-[#21262d] border border-[#30363d] text-gray-400 text-[11px]";
        catSpan.textContent = category;
        tdCat.appendChild(catSpan);

        // Status cell
        const tdStatus = document.createElement('td');
        tdStatus.className = "py-3";
        const statusSpan = document.createElement('span');
        statusSpan.className = "px-2 py-0.5 rounded bg-[#21262d] border border-[#30363d] text-emerald-400 font-medium";
        statusSpan.textContent = status;
        tdStatus.appendChild(statusSpan);

        // Source + Channel cell
        const tdSrc = document.createElement('td');
        tdSrc.className = "py-3 text-gray-400";
        const srcSpan = document.createElement('span');
        srcSpan.className = "text-purple-400 font-medium";
        srcSpan.textContent = source;
        tdSrc.appendChild(srcSpan);
        tdSrc.appendChild(document.createElement('br'));
        const chanSpan = document.createElement('span');
        chanSpan.className = "text-[10px] text-gray-500";
        chanSpan.textContent = `via ${channel}`;
        tdSrc.appendChild(chanSpan);

        // Notes cell
        const tdNotes = document.createElement('td');
        tdNotes.className = "py-3 text-gray-400 max-w-xs truncate italic";
        tdNotes.title = notes;
        tdNotes.textContent = notes || '—';

        tr.append(tdDate, tdUpdate, tdTitle, tdCat, tdStatus, tdSrc, tdNotes);
        tableBody.appendChild(tr);
    });
}