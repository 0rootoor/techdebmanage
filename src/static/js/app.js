// Déclarées en tout premier pour ne jamais rester bloquées dans la zone
// morte temporelle si une ligne plus bas venait à lever une erreur
// (ex : Chart.js indisponible suite à un souci de CDN).
let chartsInitialized = false;
let ganttInitialized = false;

let CHART_DATA = {};
try {
    const el = document.getElementById('chart-data');
    if (el) CHART_DATA = JSON.parse(el.textContent);
} catch (e) {
    console.error("Impossible de charger chart-data", e);
}

const PALETTE = ['#1256A3', '#2E86DE', '#6FA8DC', '#0B2545', '#8FB8E8'];

// Chart.js est chargé depuis un CDN externe : si ce chargement échoue
// (réseau, CDN indisponible...), on ne doit pas casser le reste de la page
// (filtres, Gantt, édition...), donc on protège cet appel.
if (typeof Chart !== 'undefined') {
    Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.color = '#64748B';
} else {
    console.error("Chart.js n'a pas pu être chargé depuis le CDN : les graphiques de l'onglet Statistiques ne s'afficheront pas, mais le reste de l'application fonctionne normalement.");
}

function initCharts() {
    if (chartsInitialized) return;
    const anyCanvas = document.getElementById('chartCategory') || document.getElementById('chartSocle');
    if (!anyCanvas) return;
    if (typeof Chart === 'undefined') {
        anyCanvas.closest('.chart-grid').innerHTML = `<div class="empty-state" style="grid-column:1/-1; color:var(--danger);">
                    Impossible de charger la librairie de graphiques (Chart.js) depuis le CDN. Vérifie ta connexion internet ou ouvre la console du navigateur (F12) pour plus de détails.
                </div>`;
        return;
    }
    chartsInitialized = true;

    if (document.getElementById('chartCategory')) {
        new Chart(document.getElementById('chartCategory'), {
            type: 'doughnut',
            data: {
                labels: CHART_DATA.categoryLabels,
                datasets: [{ data: CHART_DATA.categoryCounts, backgroundColor: PALETTE, borderWidth: 0 }]
            },
            options: { plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 12 } } }, cutout: '65%' }
        });
    }

    if (document.getElementById('chartImpact')) {
        new Chart(document.getElementById('chartImpact'), {
            type: 'bar',
            data: {
                labels: CHART_DATA.impactLabels,
                datasets: [{ data: CHART_DATA.impactCounts, backgroundColor: ['#157A5C', '#B5730A', '#C0362C'], borderRadius: 6, maxBarThickness: 48 }]
            },
            options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { grid: { display: false } } } }
        });
    }

    if (document.getElementById('chartCost')) {
        new Chart(document.getElementById('chartCost'), {
            type: 'bar',
            data: {
                labels: CHART_DATA.categoryLabels,
                datasets: [{ label: 'Jours', data: CHART_DATA.costByCategory, backgroundColor: '#1256A3', borderRadius: 6, maxBarThickness: 40 }]
            },
            options: { indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, ticks: { precision: 0 } } } }
        });
    }

    if (document.getElementById('chartStatus')) {
        new Chart(document.getElementById('chartStatus'), {
            type: 'doughnut',
            data: {
                labels: CHART_DATA.statusLabels,
                datasets: [{ data: CHART_DATA.statusCounts, backgroundColor: ['#B5730A', '#2E86DE', '#157A5C'], borderWidth: 0 }]
            },
            options: { plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 12 } } }, cutout: '65%' }
        });
    }

    if (document.getElementById('chartSocle')) {
        new Chart(document.getElementById('chartSocle'), {
            type: 'doughnut',
            data: {
                labels: CHART_DATA.socleLabels,
                datasets: [{ data: CHART_DATA.socleCounts, backgroundColor: PALETTE, borderWidth: 0 }]
            },
            options: { plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 12 } } }, cutout: '65%' }
        });
    }

    if (document.getElementById('chartFramework')) {
        new Chart(document.getElementById('chartFramework'), {
            type: 'doughnut',
            data: {
                labels: CHART_DATA.frameworkLabels,
                datasets: [{ data: CHART_DATA.frameworkCounts, backgroundColor: PALETTE, borderWidth: 0 }]
            },
            options: { plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 12 } } }, cutout: '65%' }
        });
    }

    if (document.getElementById('chartAppStatus')) {
        const appStatusColors = { 'En projet': '#1256A3', 'En développement': '#B5730A', 'En production': '#157A5C', 'En maintenance': '#B5730A', 'Décommissionnée': '#94A3B8' };
        new Chart(document.getElementById('chartAppStatus'), {
            type: 'bar',
            data: {
                labels: CHART_DATA.appStatusLabels,
                datasets: [{ data: CHART_DATA.appStatusCounts, backgroundColor: CHART_DATA.appStatusLabels.map(l => appStatusColors[l] || '#1256A3'), borderRadius: 6, maxBarThickness: 44 }]
            },
            options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { grid: { display: false } } } }
        });
    }
}

function exportChartImage(canvasId, filename) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const link = document.createElement('a');
    link.download = filename + '.png';
    link.href = canvas.toDataURL('image/png', 1.0);
    link.click();
}

function applyFilters() {
    const search = document.getElementById('filterSearch').value.trim().toLowerCase();
    const project = document.getElementById('filterProject').value;
    const appStatus = document.getElementById('filterAppStatus').value;
    const socle = document.getElementById('filterSocle').value;
    const framework = document.getElementById('filterFramework').value;
    const category = document.getElementById('filterCategory').value;
    const impact = document.getElementById('filterImpact').value;
    const status = document.getElementById('filterStatus').value;
    const pilotOnly = document.getElementById('filterPilotOnly').checked;

    const rows = document.querySelectorAll('#debtsTableBody tr[data-project]');
    const summary = document.getElementById('filterSummary');
    if (rows.length === 0) {
        summary.innerHTML = '';
        return;
    }
    let visibleCount = 0;
    let visibleCost = 0;

    rows.forEach(row => {
        const matches = (
            (!search || row.dataset.search.includes(search)) &&
            (!project || row.dataset.project === project) &&
            (!appStatus || row.dataset.appStatus === appStatus) &&
            (!socle || row.dataset.socle === socle) &&
            (!framework || row.dataset.framework === framework) &&
            (!category || row.dataset.category === category) &&
            (!impact || row.dataset.impact === impact) &&
            (!status || row.dataset.status === status) &&
            (!pilotOnly || row.dataset.pilot === 'true')
        );
        row.classList.toggle('filtered-out', !matches);
        if (matches) {
            visibleCount++;
            visibleCost += parseFloat(row.dataset.cost || '0');
        }
    });

    const totalCount = rows.length;
    if (visibleCount === totalCount) {
        summary.innerHTML = `<strong>${totalCount}</strong> dette(s) au total — charge : <strong>${visibleCost}</strong> jours`;
    } else {
        summary.innerHTML = `<strong>${visibleCount}</strong> dette(s) affichée(s) sur ${totalCount} — charge filtrée : <strong>${visibleCost}</strong> jours`;
    }

    syncFiltersToUrl();
}

function syncFiltersToUrl() {
    const params = new URLSearchParams(window.location.search);
    const map = {
        search: document.getElementById('filterSearch').value.trim(),
        project: document.getElementById('filterProject').value,
        appStatus: document.getElementById('filterAppStatus').value,
        socle: document.getElementById('filterSocle').value,
        framework: document.getElementById('filterFramework').value,
        category: document.getElementById('filterCategory').value,
        impact: document.getElementById('filterImpact').value,
        status: document.getElementById('filterStatus').value,
        pilotOnly: document.getElementById('filterPilotOnly').checked ? '1' : '',
    };
    Object.entries(map).forEach(([key, value]) => {
        if (value) params.set(key, value); else params.delete(key);
    });
    history.replaceState(null, '', '?' + params.toString());
}

function loadFiltersFromUrl() {
    const params = new URLSearchParams(window.location.search);
    if (params.has('search')) document.getElementById('filterSearch').value = params.get('search');
    if (params.has('project')) document.getElementById('filterProject').value = params.get('project');
    if (params.has('appStatus')) document.getElementById('filterAppStatus').value = params.get('appStatus');
    if (params.has('socle')) document.getElementById('filterSocle').value = params.get('socle');
    if (params.has('framework')) document.getElementById('filterFramework').value = params.get('framework');
    if (params.has('category')) document.getElementById('filterCategory').value = params.get('category');
    if (params.has('impact')) document.getElementById('filterImpact').value = params.get('impact');
    if (params.has('status')) document.getElementById('filterStatus').value = params.get('status');
    if (params.get('pilotOnly') === '1') document.getElementById('filterPilotOnly').checked = true;
    const tab = params.get('tab');
    if (tab && tab !== 'register') switchTab(tab);
}

function resetFilters() {
    document.getElementById('filterSearch').value = '';
    document.getElementById('filterProject').value = '';
    document.getElementById('filterAppStatus').value = '';
    document.getElementById('filterSocle').value = '';
    document.getElementById('filterFramework').value = '';
    document.getElementById('filterCategory').value = '';
    document.getElementById('filterImpact').value = '';
    document.getElementById('filterStatus').value = '';
    document.getElementById('filterPilotOnly').checked = false;
    applyFilters();
}

// --- Tri des colonnes du registre ---
const IMPACT_RANK = { 'Faible': 0, 'Moyen': 1, 'Élevé': 2 };
const STATUS_RANK = { 'Ouverte': 0, 'En cours': 1, 'Résolue': 2 };
let currentSort = { key: null, dir: 1 };

function sortTable(key) {
    const tbody = document.getElementById('debtsTableBody');
    const rows = Array.from(tbody.querySelectorAll('tr[data-project]'));
    if (!rows.length) return;

    if (currentSort.key === key) {
        currentSort.dir *= -1;
    } else {
        currentSort = { key, dir: 1 };
    }

    const getValue = (row) => {
        if (key === 'cost') return parseFloat(row.dataset.cost || '0');
        if (key === 'impact') return IMPACT_RANK[row.dataset.impact] ?? -1;
        if (key === 'status') return STATUS_RANK[row.dataset.status] ?? -1;
        if (key === 'title') return row.dataset.title || '';
        return '';
    };

    rows.sort((a, b) => {
        const va = getValue(a), vb = getValue(b);
        if (va < vb) return -1 * currentSort.dir;
        if (va > vb) return 1 * currentSort.dir;
        return 0;
    });
    rows.forEach(row => tbody.appendChild(row));

    document.querySelectorAll('th.sortable .sort-arrow').forEach(el => el.innerText = '');
    const activeHeader = document.querySelector(`th.sortable[data-sort-key="${key}"] .sort-arrow`);
    if (activeHeader) activeHeader.innerText = currentSort.dir === 1 ? '▲' : '▼';
}

// --- Export du registre (respecte les filtres actifs) ---
function exportRegistre(format) {
    const rows = document.querySelectorAll('#debtsTableBody tr[data-project]:not(.filtered-out)');
    if (!rows.length) {
        alert("Aucune dette à exporter avec les filtres actuels.");
        return;
    }
    const ids = Array.from(rows).map(r => r.dataset.id).join(',');
    window.location.href = `/api/debts/export?ids=${ids}&format=${format}`;
}

function switchTab(tab) {
    const views = {
        register: document.getElementById('tab-register'), planning: document.getElementById('tab-planning'),
        gantt: document.getElementById('tab-gantt'), portfolio: document.getElementById('tab-portfolio'),
        alerts: document.getElementById('tab-alerts'), history: document.getElementById('tab-history'),
        users: document.getElementById('tab-users'),
        stats: document.getElementById('tab-stats'),
    };
    const btns = {
        register: document.getElementById('btn-register'), planning: document.getElementById('btn-planning'),
        gantt: document.getElementById('btn-gantt'), portfolio: document.getElementById('btn-portfolio'),
        alerts: document.getElementById('btn-alerts'), history: document.getElementById('btn-history'),
        users: document.getElementById('btn-users'),
        stats: document.getElementById('btn-stats'),
    };

    Object.keys(views).forEach(key => {
        if (!views[key] || !btns[key]) return; // onglet absent du DOM (ex: Utilisateurs pour un non-admin)
        views[key].style.display = (key === tab) ? (key === 'register' ? 'grid' : 'block') : 'none';
        btns[key].classList.toggle('active', key === tab);
    });

    if (tab === 'stats') initCharts();
    if (tab === 'gantt') initGantt();

    const params = new URLSearchParams(window.location.search);
    params.set('tab', tab);
    history.replaceState(null, '', '?' + params.toString());
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function initGantt() {
    if (ganttInitialized) return;
    const container = document.getElementById('ganttContainer');
    if (!container) return;
    ganttInitialized = true;

    try {
        renderGantt(container);
    } catch (err) {
        console.error('Erreur lors du rendu du Gantt :', err);
        container.innerHTML = `<div class="empty-state" style="color:var(--danger);">
                    Une erreur est survenue lors de l'affichage du Gantt : ${escapeHtml(err.message)}.<br>
                    Ouvre la console du navigateur (F12) pour plus de détails.
                </div>`;
        ganttInitialized = false; // permet de réessayer si on rouvre l'onglet après correction
    }
}

function renderGantt(container) {
    const dataEl = document.getElementById('gantt-data');
    if (!dataEl) throw new Error("bloc de données gantt-data introuvable dans la page");
    const rows = JSON.parse(dataEl.textContent);
    const milestonesEl = document.getElementById('milestones-data');
    const milestones = milestonesEl ? JSON.parse(milestonesEl.textContent) : [];
    if (!rows.length) {
        container.innerHTML = `<div class="empty-state">Aucune donnée de planification à afficher pour le moment.</div>`;
        return;
    }

    const impactColor = { 'Faible': '#157A5C', 'Moyen': '#B5730A', 'Élevé': '#C0362C' };
    const parseDate = (s) => new Date(s + 'T00:00:00');

    const starts = rows.map(r => parseDate(r.start).getTime());
    const ends = rows.map(r => parseDate(r.end).getTime());
    const milestoneTimes = milestones.map(m => parseDate(m.date).getTime());
    const today = new Date(); today.setHours(0, 0, 0, 0);
    let minTime = Math.min(...starts, today.getTime(), ...(milestoneTimes.length ? milestoneTimes : [today.getTime()]));
    let maxTime = Math.max(...ends, today.getTime(), ...(milestoneTimes.length ? milestoneTimes : [today.getTime()]));

    // Marge de quelques jours de chaque côté pour la lisibilité
    const DAY = 86400000;
    minTime -= 3 * DAY;
    maxTime += 3 * DAY;
    const totalDays = Math.max(1, Math.round((maxTime - minTime) / DAY));

    const PX_PER_DAY = totalDays > 240 ? 4 : (totalDays > 120 ? 7 : 12);
    const timelineWidth = totalDays * PX_PER_DAY;
    const LABEL_WIDTH = 260;

    const dayOffset = (t) => Math.round((t - minTime) / DAY) * PX_PER_DAY;

    // En-tête : un repère par mois
    let monthTicks = '';
    let cursor = new Date(minTime);
    cursor.setDate(1);
    const monthNames = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
    let safety = 0;
    while (cursor.getTime() < maxTime && safety < 500) {
        const offset = dayOffset(cursor.getTime());
        if (offset >= 0) {
            monthTicks += `<div class="gantt-month-tick" style="left:${offset}px;">${monthNames[cursor.getMonth()]} ${cursor.getFullYear()}</div>`;
        }
        cursor.setMonth(cursor.getMonth() + 1);
        safety++;
    }

    const todayOffset = dayOffset(today.getTime());

    let rowsHtml = '';
    rows.forEach(r => {
        const startOffset = dayOffset(parseDate(r.start).getTime());
        const endOffset = dayOffset(parseDate(r.end).getTime());
        const width = Math.max(endOffset - startOffset, 8);
        const color = impactColor[r.impact] || '#1256A3';
        const pilotTag = r.isPilot ? '<span class="pill pill-pilot" style="font-size:9px; padding:1px 5px; margin-left:5px;">Pilote</span>' : '';
        rowsHtml += `
                <div class="gantt-row">
                    <div class="gantt-row-label" style="width:${LABEL_WIDTH}px;">
                        <div class="g-title">${escapeHtml(r.title)}</div>
                        <div class="g-app">${escapeHtml(r.project)}${pilotTag}</div>
                    </div>
                    <div class="gantt-track">
                        <div class="gantt-bar ${r.estimated ? 'estimated' : ''}" style="left:${startOffset}px; width:${width}px; background:${color};" title="${escapeHtml(r.title)} — ${escapeHtml(r.assignee)} — ${r.costDays}j — ${r.status}${r.estimated ? ' (échéance estimée)' : ''}">
                            ${width > 60 ? escapeHtml(r.status) : ''}
                        </div>
                    </div>
                </div>`;
    });

    let milestonesHtml = '';
    milestones.forEach(m => {
        const offset = dayOffset(parseDate(m.date).getTime());
        const tooltip = `${m.label} — ${m.date}${m.project ? ' — ' + m.project : ''}`;
        milestonesHtml += `
                    <div class="gantt-milestone-line" style="left:${LABEL_WIDTH + offset}px;" title="${escapeHtml(tooltip)}">
                        <div class="gantt-milestone-flag">🚩</div>
                    </div>`;
    });

    container.innerHTML = `
                <div style="min-width:${LABEL_WIDTH + timelineWidth}px;">
                    <div class="gantt-header">
                        <div class="gantt-header-label" style="width:${LABEL_WIDTH}px;">Dette</div>
                        <div class="gantt-header-months" style="width:${timelineWidth}px;">${monthTicks}</div>
                    </div>
                    <div style="position:relative;">
                        <div class="gantt-today-line" style="left:${LABEL_WIDTH + todayOffset}px;">
                            <div class="gantt-today-label" style="left:-14px;">Auj.</div>
                        </div>
                        ${milestonesHtml}
                        ${rowsHtml}
                    </div>
                </div>`;
}

async function submitMilestone(form) {
    const label = document.getElementById('milestone_label').value;
    const milestoneDate = document.getElementById('milestone_date').value;
    const projectId = document.getElementById('milestone_project_id').value;
    const params = `label=${encodeURIComponent(label)}&milestone_date=${encodeURIComponent(milestoneDate)}` + (projectId ? `&project_id=${projectId}` : '');
    const res = await fetch(`/api/milestones?${params}`, { method: 'POST' });
    if (res.ok) {
        window.location.reload();
    } else {
        const data = await res.json();
        alert("Erreur : " + data.detail);
    }
}

async function deleteMilestoneUI(id) {
    if (!confirm("Supprimer ce jalon ?")) return;
    const res = await fetch(`/api/milestones/${id}`, { method: 'DELETE' });
    if (res.ok) {
        window.location.reload();
    } else {
        alert("Erreur lors de la suppression.");
    }
}

function exportGanttPdf() {
    document.body.classList.add('printing-gantt');
    window.print();
    setTimeout(() => document.body.classList.remove('printing-gantt'), 500);
}

function openEditDebt(id, projectId, title, category, impact, costDays, assignee, startDate, targetDate) {
    document.getElementById('debt_id').value = id;
    document.getElementById('debt_project_id').value = projectId;
    document.getElementById('debt_title').value = title;
    document.getElementById('debt_category').value = category;
    document.getElementById('debt_impact').value = impact;
    document.getElementById('debt_cost_days').value = costDays;
    document.getElementById('debt_assignee').value = assignee;
    document.getElementById('debt_start_date').value = startDate;
    document.getElementById('debt_target_date').value = targetDate;

    document.getElementById('debt-form-title').innerText = "Modifier la dette";
    document.getElementById('debt-submit-btn').innerText = "Mettre à jour";
    document.getElementById('debt-cancel-btn').style.display = 'inline-block';
    switchTab('register');
    document.getElementById('debt-form-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function resetDebtForm() {
    document.getElementById('debt_id').value = '';
    document.getElementById('debt_project_id').value = '';
    document.getElementById('debt_title').value = '';
    document.getElementById('debt_category').value = 'Code';
    document.getElementById('debt_impact').value = 'Moyen';
    document.getElementById('debt_cost_days').value = '';
    document.getElementById('debt_assignee').value = '';
    document.getElementById('debt_start_date').value = '';
    document.getElementById('debt_target_date').value = '';

    document.getElementById('debt-form-title').innerText = "Déclarer une dette";
    document.getElementById('debt-submit-btn').innerText = "Ajouter la dette";
    document.getElementById('debt-cancel-btn').style.display = 'none';
}

function openEditProject(id, name, description, isPilot, appStatus, socle, framework) {
    switchTab('register');

    document.getElementById('project_id').value = id;
    document.getElementById('project_name').value = name;
    document.getElementById('project_description').value = description;
    document.getElementById('project_is_pilot').checked = isPilot;
    document.getElementById('project_app_status').value = appStatus;
    document.getElementById('project_socle').value = socle;
    document.getElementById('project_framework').value = framework;

    document.getElementById('project-form-title').innerText = "Modifier l'application";
    document.getElementById('project-submit-btn').innerText = "Mettre à jour";
    document.getElementById('project-cancel-btn').style.display = 'inline-block';
    document.getElementById('project-form-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function resetProjectForm() {
    document.getElementById('project_id').value = '';
    document.getElementById('project_name').value = '';
    document.getElementById('project_description').value = '';
    document.getElementById('project_is_pilot').checked = false;
    document.getElementById('project_app_status').value = 'En projet';
    document.getElementById('project_socle').value = '';
    document.getElementById('project_framework').value = '';

    document.getElementById('project-form-title').innerText = "Ajouter une application";
    document.getElementById('project-submit-btn').innerText = "Enregistrer l'app";
    document.getElementById('project-cancel-btn').style.display = 'none';
}

async function saveProject(form) {
    const id = document.getElementById('project_id').value;
    const name = document.getElementById('project_name').value;
    const description = document.getElementById('project_description').value;
    const isPilot = document.getElementById('project_is_pilot').checked;
    const appStatus = document.getElementById('project_app_status').value;
    const socle = document.getElementById('project_socle').value;
    const framework = document.getElementById('project_framework').value;

    const params = `name=${encodeURIComponent(name)}&description=${encodeURIComponent(description)}&is_pilot=${isPilot}&app_status=${encodeURIComponent(appStatus)}&socle=${encodeURIComponent(socle)}&framework=${encodeURIComponent(framework)}`;
    const url = id ? `/api/projects/${id}?${params}` : `/api/projects?${params}`;
    const method = id ? 'PUT' : 'POST';

    const res = await fetch(url, { method: method });
    if (res.ok) {
        resetProjectForm();
        window.location.reload();
    } else {
        const err = await res.json();
        alert("Erreur : " + err.detail);
    }
}

async function deleteProject(id, name, debtCount) {
    let message = `Supprimer l'application "${name}" ?`;
    if (debtCount > 0) {
        message += `\n\n⚠️ ${debtCount} dette(s) technique(s) rattachée(s) à cette application seront aussi supprimée(s) définitivement.`;
    }
    if (!confirm(message)) return;

    const res = await fetch(`/api/projects/${id}`, { method: 'DELETE' });
    if (res.ok) {
        window.location.reload();
    } else {
        const err = await res.json();
        alert("Erreur : " + err.detail);
    }
}

async function saveDebt(form) {
    const id = document.getElementById('debt_id').value;
    const formData = new FormData(form);
    const params = new URLSearchParams();
    for (const pair of formData.entries()) {
        if (pair[0] !== 'debt_id') {
            params.append(pair[0], pair[1]);
        }
    }

    let url = `/api/debts?${params.toString()}`;
    let method = 'POST';

    if (id) {
        url = `/api/debts/${id}?${params.toString()}`;
        method = 'PUT';
    }

    const res = await fetch(url, { method: method });
    if (res.ok) {
        resetDebtForm();
        window.location.reload();
    } else {
        alert("Erreur lors de l'enregistrement de la dette");
    }
}

async function deleteDebt(id) {
    if (!confirm("Voulez-vous vraiment supprimer cette dette ?")) return;

    const res = await fetch(`/api/debts/${id}`, { method: 'DELETE' });
    if (res.ok) {
        window.location.reload();
    } else {
        alert("Erreur lors de la suppression");
    }
}

async function updateStatus(id, newStatus) {
    await fetch(`/api/debts/${id}/status?status=${encodeURIComponent(newStatus)}`, {
        method: 'PATCH'
    });
}

async function sendSlackAlert() {
    const msgEl = document.getElementById('slackAlertMessage');
    msgEl.style.color = 'var(--muted)';
    msgEl.innerText = 'Envoi en cours…';
    try {
        const res = await fetch('/api/alerts/send', { method: 'POST' });
        const data = await res.json();
        msgEl.style.color = data.sent ? 'var(--success)' : 'var(--danger)';
        msgEl.innerText = data.message;
    } catch (err) {
        msgEl.style.color = 'var(--danger)';
        msgEl.innerText = "Erreur réseau lors de l'envoi.";
    }
}

async function createUser(form) {
    const username = document.getElementById('new_user_username').value;
    const password = document.getElementById('new_user_password').value;
    const role = document.getElementById('new_user_role').value;
    const msgEl = document.getElementById('userFormMessage');

    const params = `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}&role=${encodeURIComponent(role)}`;
    const res = await fetch(`/api/users?${params}`, { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
        window.location.reload();
    } else {
        msgEl.style.color = 'var(--danger)';
        msgEl.innerText = data.detail;
    }
}

async function updateUserRole(userId, role) {
    const res = await fetch(`/api/users/${userId}?role=${encodeURIComponent(role)}`, { method: 'PUT' });
    if (res.ok) {
        window.location.reload();
    } else {
        const data = await res.json();
        alert("Erreur : " + data.detail);
    }
}

async function deleteUser(userId, username) {
    if (!confirm(`Supprimer le compte "${username}" ?`)) return;
    const res = await fetch(`/api/users/${userId}`, { method: 'DELETE' });
    if (res.ok) {
        window.location.reload();
    } else {
        const data = await res.json();
        alert("Erreur : " + data.detail);
    }
}

async function uploadFile() {
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/api/projects/import', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (res.ok) {
            document.getElementById('importMessage').innerText = data.message;
            document.getElementById('importMessage').style.color = 'var(--success)';
            setTimeout(() => window.location.reload(), 1500);
        } else {
            document.getElementById('importMessage').innerText = 'Erreur : ' + data.detail;
            document.getElementById('importMessage').style.color = 'var(--danger)';
        }
    } catch (err) {
        document.getElementById('importMessage').innerText = 'Erreur réseau.';
        document.getElementById('importMessage').style.color = 'var(--danger)';
    }
}

// --- Modale Commentaires & Liens ---
let currentDetailsDebtId = null;

function escapeHtmlText(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

async function openDetailsModal(debtId, debtTitle) {
    currentDetailsDebtId = debtId;
    document.getElementById('detailsModalTitle').innerText = debtTitle;
    document.getElementById('newLinkLabel').value = '';
    document.getElementById('newLinkUrl').value = '';
    document.getElementById('newCommentContent').value = '';
    document.getElementById('detailsModalOverlay').style.display = 'flex';
    await Promise.all([loadLinks(), loadComments()]);
}

function closeDetailsModal() {
    document.getElementById('detailsModalOverlay').style.display = 'none';
    currentDetailsDebtId = null;
}

function getLinkIcon(url) {
    const u = url.toLowerCase();
    if (u.includes('jira') || u.includes('atlassian')) return '🎫';
    if (u.includes('github.com') && u.includes('/pull/')) return '🔀';
    if (u.includes('github.com')) return '🐙';
    if (u.includes('gitlab.com') && (u.includes('/merge_requests/') || u.includes('/-/merge_requests'))) return '🔀';
    if (u.includes('gitlab.com')) return '🦊';
    if (u.includes('confluence')) return '📘';
    if (u.includes('docs.google') || u.includes('sharepoint') || u.includes('.pdf')) return '📄';
    return '🔗';
}

function getLinkDomain(url) {
    try {
        return new URL(url).hostname.replace(/^www\./, '');
    } catch (err) {
        return url;
    }
}

async function loadLinks() {
    const container = document.getElementById('linksList');
    container.innerHTML = '<div class="empty-mini">Chargement…</div>';
    try {
        const res = await fetch(`/api/debts/${currentDetailsDebtId}/links`);
        const links = await res.json();
        if (!links.length) {
            container.innerHTML = '<div class="empty-mini">Aucun lien pour le moment.</div>';
            return;
        }
        container.innerHTML = links.map(l => `
                    <div class="link-item">
                        <span class="link-icon">${getLinkIcon(l.url)}</span>
                        <div class="link-item-text">
                            <a href="${escapeHtmlText(l.url)}" target="_blank" rel="noopener noreferrer">${escapeHtmlText(l.label)}</a>
                            <div class="link-item-domain">${escapeHtmlText(getLinkDomain(l.url))}</div>
                        </div>
                        ${CURRENT_ROLE !== 'lecture_seule' ? `<button class="item-delete-btn" onclick="deleteLinkUI(${l.id})">Supprimer</button>` : ''}
                    </div>
                `).join('');
    } catch (err) {
        container.innerHTML = '<div class="empty-mini">Erreur de chargement.</div>';
    }
}

async function loadComments() {
    const container = document.getElementById('commentsList');
    container.innerHTML = '<div class="empty-mini">Chargement…</div>';
    try {
        const res = await fetch(`/api/debts/${currentDetailsDebtId}/comments`);
        const comments = await res.json();
        if (!comments.length) {
            container.innerHTML = '<div class="empty-mini">Aucun commentaire pour le moment.</div>';
            return;
        }
        container.innerHTML = comments.map(c => `
                    <div class="comment-item">
                        <div class="comment-body">
                            <div class="comment-meta"><strong>${escapeHtmlText(c.username)}</strong> — ${c.created_at}</div>
                            <div class="comment-content">${escapeHtmlText(c.content)}</div>
                        </div>
                        ${(CURRENT_ROLE !== 'lecture_seule' && (c.username === CURRENT_USER || CURRENT_ROLE === 'admin')) ? `<button class="item-delete-btn" onclick="deleteCommentUI(${c.id})">Supprimer</button>` : ''}
                    </div>
                `).join('');
    } catch (err) {
        container.innerHTML = '<div class="empty-mini">Erreur de chargement.</div>';
    }
}

async function submitLink() {
    const label = document.getElementById('newLinkLabel').value.trim();
    const url = document.getElementById('newLinkUrl').value.trim();
    if (!label || !url) { alert("Le libellé et l'URL sont requis."); return; }
    const res = await fetch(`/api/debts/${currentDetailsDebtId}/links?label=${encodeURIComponent(label)}&url=${encodeURIComponent(url)}`, { method: 'POST' });
    if (res.ok) {
        document.getElementById('newLinkLabel').value = '';
        document.getElementById('newLinkUrl').value = '';
        await loadLinks();
    } else {
        const data = await res.json();
        alert("Erreur : " + data.detail);
    }
}

async function deleteLinkUI(linkId) {
    if (!confirm("Supprimer ce lien ?")) return;
    const res = await fetch(`/api/links/${linkId}`, { method: 'DELETE' });
    if (res.ok) { await loadLinks(); } else { alert("Erreur lors de la suppression."); }
}

async function submitComment() {
    const content = document.getElementById('newCommentContent').value.trim();
    if (!content) return;
    const res = await fetch(`/api/debts/${currentDetailsDebtId}/comments?content=${encodeURIComponent(content)}`, { method: 'POST' });
    if (res.ok) {
        document.getElementById('newCommentContent').value = '';
        await loadComments();
    } else {
        const data = await res.json();
        alert("Erreur : " + data.detail);
    }
}

async function deleteCommentUI(commentId) {
    if (!confirm("Supprimer ce commentaire ?")) return;
    const res = await fetch(`/api/comments/${commentId}`, { method: 'DELETE' });
    if (res.ok) { await loadComments(); } else { alert("Erreur lors de la suppression."); }
}

function applyPlanningFilters() {
    const search = document.getElementById('filterPlanningSearch').value.trim().toLowerCase();
    const project = document.getElementById('filterPlanningProject').value;
    const appStatus = document.getElementById('filterPlanningAppStatus').value;
    const socle = document.getElementById('filterPlanningSocle').value;
    const framework = document.getElementById('filterPlanningFramework').value;
    const category = document.getElementById('filterPlanningCategory').value;
    const impact = document.getElementById('filterPlanningImpact').value;
    const status = document.getElementById('filterPlanningStatus').value;
    const minStart = document.getElementById('filterPlanningMinStart').value;
    const maxTarget = document.getElementById('filterPlanningMaxTarget').value;
    const pilotOnly = document.getElementById('filterPlanningPilotOnly').checked;

    const cards = document.querySelectorAll('#tab-planning .plan-card');
    const summary = document.getElementById('filterPlanningSummary');
    if (cards.length === 0) {
        if (summary) summary.innerHTML = '';
        return;
    }
    let visibleCount = 0;
    let visibleCost = 0;

    cards.forEach(card => {
        const matches = (
            (!search || card.dataset.search.includes(search)) &&
            (!project || card.dataset.project === project) &&
            (!appStatus || card.dataset.appStatus === appStatus) &&
            (!socle || card.dataset.socle === socle) &&
            (!framework || card.dataset.framework === framework) &&
            (!category || card.dataset.category === category) &&
            (!impact || card.dataset.impact === impact) &&
            (!status || card.dataset.status === status) &&
            (!minStart || (card.dataset.startDate && card.dataset.startDate >= minStart)) &&
            (!maxTarget || (card.dataset.targetDate && card.dataset.targetDate <= maxTarget)) &&
            (!pilotOnly || card.dataset.pilot === 'true')
        );
        card.classList.toggle('filtered-out', !matches);
        if (matches) {
            visibleCount++;
            visibleCost += parseFloat(card.dataset.cost || '0');
        }
    });

    const totalCount = cards.length;
    if (summary) {
        if (visibleCount === totalCount) {
            summary.innerHTML = `<strong>${totalCount}</strong> dette(s) au total — charge : <strong>${visibleCost}</strong> jours`;
        } else {
            summary.innerHTML = `<strong>${visibleCount}</strong> dette(s) affichée(s) sur ${totalCount} — charge filtrée : <strong>${visibleCost}</strong> jours`;
        }
    }
}

function resetPlanningFilters() {
    document.getElementById('filterPlanningSearch').value = '';
    document.getElementById('filterPlanningProject').value = '';
    document.getElementById('filterPlanningAppStatus').value = '';
    document.getElementById('filterPlanningSocle').value = '';
    document.getElementById('filterPlanningFramework').value = '';
    document.getElementById('filterPlanningCategory').value = '';
    document.getElementById('filterPlanningImpact').value = '';
    document.getElementById('filterPlanningStatus').value = '';
    document.getElementById('filterPlanningMinStart').value = '';
    document.getElementById('filterPlanningMaxTarget').value = '';
    document.getElementById('filterPlanningPilotOnly').checked = false;
    applyPlanningFilters();
}

function applyPortfolioFilters() {
    const search = document.getElementById('filterPortfolioSearch').value.trim().toLowerCase();
    const appStatus = document.getElementById('filterPortfolioAppStatus').value;
    const socle = document.getElementById('filterPortfolioSocle').value;
    const framework = document.getElementById('filterPortfolioFramework').value;
    const pilotOnly = document.getElementById('filterPortfolioPilotOnly').checked;

    const rows = document.querySelectorAll('#tab-portfolio tbody tr');
    const summary = document.getElementById('filterPortfolioSummary');
    if (rows.length === 0) {
        if (summary) summary.innerHTML = '';
        return;
    }
    let visibleCount = 0;
    let visibleCost = 0;
    let visibleDebts = 0;

    rows.forEach(row => {
        if (!row.dataset.appStatus) return;
        const matches = (
            (!search || row.dataset.search.includes(search)) &&
            (!appStatus || row.dataset.appStatus === appStatus) &&
            (!socle || row.dataset.socle === socle) &&
            (!framework || row.dataset.framework === framework) &&
            (!pilotOnly || row.dataset.pilot === 'true')
        );
        row.classList.toggle('filtered-out', !matches);
        if (matches) {
            visibleCount++;
            visibleCost += parseFloat(row.dataset.cost || '0');
            visibleDebts += parseInt(row.dataset.debtCount || '0', 10);
        }
    });

    const totalCount = document.querySelectorAll('#tab-portfolio tbody tr[data-app-status]').length;
    if (summary) {
        if (visibleCount === totalCount) {
            summary.innerHTML = `<strong>${totalCount}</strong> application(s) au total — ${visibleDebts} dette(s), charge : <strong>${visibleCost}</strong> jours`;
        } else {
            summary.innerHTML = `<strong>${visibleCount}</strong> application(s) affichée(s) sur ${totalCount} — ${visibleDebts} dette(s), charge filtrée : <strong>${visibleCost}</strong> jours`;
        }
    }
}

function resetPortfolioFilters() {
    document.getElementById('filterPortfolioSearch').value = '';
    document.getElementById('filterPortfolioAppStatus').value = '';
    document.getElementById('filterPortfolioSocle').value = '';
    document.getElementById('filterPortfolioFramework').value = '';
    document.getElementById('filterPortfolioPilotOnly').checked = false;
    applyPortfolioFilters();
}

loadFiltersFromUrl();
applyFilters();
applyPlanningFilters();
applyPortfolioFilters();
