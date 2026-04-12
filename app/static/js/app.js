/**
 * app.js — Dashboard SPA logic
 * Manages sections, data loading, modals, toasts, analytics
 */

let currentUser = null;
let currentSection = 'home';
let analyticsTab = 'shift';
let analyticsPeriod = 'day';
let shiftHours = 12;

document.addEventListener('DOMContentLoaded', async () => {
    // Check auth
    const token = API.getToken();
    if (!token) { window.location.href = '/'; return; }

    currentUser = API.getUser();
    if (!currentUser) {
        const data = await API.get('/api/me');
        if (!data) return;
        currentUser = data;
        API.setUser(data);
    }

    initUI();
    showSection('home');
});

/* ===================== UI Init ===================== */
function initUI() {
    // User info
    document.getElementById('user-display-name').textContent = currentUser.username;
    document.getElementById('user-display-role').textContent = getRoleName(currentUser.role);

    // Mobile menu toggle
    const menuBtn = document.getElementById('menu-toggle');
    if (menuBtn) {
        menuBtn.addEventListener('click', () => {
            document.getElementById('sidebar').classList.toggle('open');
        });
    }

    // Role-based visibility
    applyRoleVisibility();

    // Init drag-and-drop zones
    initDragDrop();
}

function applyRoleVisibility() {
    const role = currentUser.role;

    // Hide elements not for this role
    document.querySelectorAll('[data-roles]').forEach(el => {
        const allowed = el.dataset.roles.split(',');
        el.style.display = allowed.includes(role) ? '' : 'none';
    });
}

function getRoleName(role) {
    return {
        admin: 'Администратор',
        manager: 'Менеджер',
        packer: 'Упаковщица',
        warehouseman: 'Кладовщик',
    }[role] || role;
}

function getRoleBadge(role) {
    return `<span class="badge badge-${role}">${getRoleName(role)}</span>`;
}

/* ===================== Navigation ===================== */
function showSection(id) {
    currentSection = id;

    // Update nav
    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.toggle('active', el.dataset.section === id);
    });

    // Hide all sections
    document.querySelectorAll('.content-section').forEach(s => s.style.display = 'none');

    const section = document.getElementById('section-' + id);
    if (section) {
        section.style.display = 'block';
        section.classList.add('animate-fade-in');
    }

    // Load data
    switch (id) {
        case 'home': loadHome(); break;
        case 'my-shipments': loadMyShipments(); break;
        case 'my-receptions': loadMyReceptions(); break;
        case 'stock': loadStock(); break;
        case 'history': loadHistory(); break;
        case 'users': loadUsers(); break;
        case 'analytics': loadAnalytics(); break;
    }

    // Close mobile menu
    document.getElementById('sidebar')?.classList.remove('open');
}

/* ===================== Toast ===================== */
function showToast(msg, type = 'success') {
    const existing = document.querySelectorAll('.toast');
    existing.forEach(t => t.remove());

    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3500);
}

/* ===================== Home ===================== */
function loadHome() {
    // Nothing to load — static buttons
}

/* ===================== Analytics ===================== */
async function loadAnalytics() {
    switch (analyticsTab) {
        case 'shift': loadShiftSummary(); break;
        case 'packers': loadPackerKPI(); break;
        case 'warehousemen': loadWarehousemanKPI(); break;
    }
}

function switchAnalyticsTab(tab) {
    analyticsTab = tab;

    // Update tab UI
    document.querySelectorAll('.analytics-tab').forEach(el => {
        el.classList.toggle('active', el.dataset.tab === tab);
    });

    // Toggle period/shift selectors
    const periodEl = document.getElementById('analytics-period');
    const shiftEl = document.getElementById('shift-hours-pills');
    if (tab === 'shift') {
        periodEl.style.display = 'none';
        shiftEl.style.display = 'flex';
    } else {
        periodEl.style.display = 'flex';
        shiftEl.style.display = 'none';
    }

    loadAnalytics();
}

function setAnalyticsPeriod(period) {
    analyticsPeriod = period;
    document.querySelectorAll('.period-pill[data-period]').forEach(el => {
        el.classList.toggle('active', el.dataset.period === period);
    });
    loadAnalytics();
}

function downloadEmployeePackingReport() {
    API.download(`/api/analytics/employee-packing-report?period=${analyticsPeriod}`, `Отчет_сотрудники_${analyticsPeriod}.xlsx`);
}

function setShiftHours(hours) {
    shiftHours = hours;
    document.querySelectorAll('.period-pill[data-hours]').forEach(el => {
        el.classList.toggle('active', parseInt(el.dataset.hours) === hours);
    });
    loadShiftSummary();
}

async function loadShiftSummary() {
    const container = document.getElementById('analytics-content');
    container.innerHTML = '<div class="skeleton" style="height:200px"></div>';

    const data = await API.get(`/api/analytics/shift-summary?hours=${shiftHours}`);
    if (!data) return;

    container.innerHTML = `
        <div class="kpi-grid">
            <div class="kpi-card success">
                <div class="kpi-value">${data.total_packed}</div>
                <div class="kpi-label">Упаковано шт.</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">${data.total_received}</div>
                <div class="kpi-label">Принято шт.</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">${data.total_boxes_processed}</div>
                <div class="kpi-label">Коробок обработано</div>
            </div>
            <div class="kpi-card ${data.total_errors > 0 ? 'danger' : ''}">
                <div class="kpi-value">${data.total_errors}</div>
                <div class="kpi-label">Ошибок (перебор)</div>
            </div>
        </div>

        <div class="section-card" style="margin-bottom:16px">
            <div class="section-title">⚡ Средняя скорость</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
                <div style="text-align:center;padding:16px;background:rgba(34,197,94,0.06);border-radius:12px;border:1px solid rgba(34,197,94,0.15)">
                    <div style="font-size:2rem;font-weight:800;color:var(--success)">${data.avg_packer_speed || 0}</div>
                    <div style="font-size:0.75rem;color:var(--text-muted);margin-top:4px;text-transform:uppercase;letter-spacing:0.5px;font-weight:600">шт/час — Упаковщицы</div>
                </div>
                <div style="text-align:center;padding:16px;background:rgba(56,189,248,0.06);border-radius:12px;border:1px solid rgba(56,189,248,0.15)">
                    <div style="font-size:2rem;font-weight:800;color:#38bdf8">${data.avg_warehouseman_speed || 0}</div>
                    <div style="font-size:0.75rem;color:var(--text-muted);margin-top:4px;text-transform:uppercase;letter-spacing:0.5px;font-weight:600">кор/час — Кладовщики</div>
                </div>
            </div>
        </div>

        <div class="section-card" style="margin-bottom:16px">
            <div class="section-title">👥 Активность персонала</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
                <div style="text-align:center;padding:12px">
                    <div style="font-size:1.8rem;font-weight:800;color:var(--accent)">${data.active_packers}</div>
                    <div style="font-size:0.8rem;color:var(--text-muted);margin-top:4px">Упаковщиц на смене</div>
                </div>
                <div style="text-align:center;padding:12px">
                    <div style="font-size:1.8rem;font-weight:800;color:#38bdf8">${data.active_warehousemen}</div>
                    <div style="font-size:0.8rem;color:var(--text-muted);margin-top:4px">Кладовщиков на смене</div>
                </div>
            </div>
        </div>

        <div class="section-card">
            <div style="font-size:0.8rem;color:var(--text-muted);text-align:center">
                Период: ${data.period_start} — ${data.period_end} (${data.period_hours}ч)
            </div>
        </div>
    `;
}

async function loadPackerKPI() {
    const container = document.getElementById('analytics-content');
    container.innerHTML = '<div class="skeleton" style="height:200px"></div>';

    const data = await API.get(`/api/analytics/packer-kpi?period=${analyticsPeriod}`);
    if (!data) return;

    if (data.length === 0) {
        container.innerHTML = '<div class="section-card"><p style="color:var(--text-muted);text-align:center;padding:24px">Нет данных за выбранный период</p></div>';
        return;
    }

    container.innerHTML = `
        <div class="section-card">
            <div class="section-title">👩‍🏭 Эффективность упаковщиц</div>
            <div style="overflow-x:auto">
                <table class="data-table">
                    <thead><tr>
                        <th>#</th>
                        <th>ФИО</th>
                        <th>Всего шт.</th>
                        <th>Скорость (шт/час)</th>
                        <th>Время (часов)</th>
                        <th>Сессий</th>
                        <th>Ошибок</th>
                    </tr></thead>
                    <tbody>
                        ${data.map((r, i) => `
                            <tr>
                                <td style="font-weight:700;color:${i < 3 ? 'var(--accent)' : 'var(--text-muted)'}">${i + 1}</td>
                                <td style="font-weight:600">${r.full_name}</td>
                                <td style="font-weight:700">${r.total_items}</td>
                                <td>
                                    <span style="font-weight:800;font-size:1.1rem;color:${r.speed_per_hour > 0 ? 'var(--success)' : 'var(--text-muted)'}">${r.speed_per_hour}</span>
                                    <span style="font-size:0.7rem;color:var(--text-muted)"> шт/ч</span>
                                </td>
                                <td style="color:var(--text-muted)">${r.total_hours}</td>
                                <td style="color:var(--text-muted)">${r.total_sessions}</td>
                                <td style="color:${r.errors > 0 ? 'var(--danger)' : 'var(--text-muted)'}; font-weight:${r.errors > 0 ? '700' : '400'}">${r.errors}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

async function loadWarehousemanKPI() {
    const container = document.getElementById('analytics-content');
    container.innerHTML = '<div class="skeleton" style="height:200px"></div>';

    const data = await API.get(`/api/analytics/warehouseman-kpi?period=${analyticsPeriod}`);
    if (!data) return;

    if (data.length === 0) {
        container.innerHTML = '<div class="section-card"><p style="color:var(--text-muted);text-align:center;padding:24px">Нет данных за выбранный период</p></div>';
        return;
    }

    container.innerHTML = `
        <div class="section-card">
            <div class="section-title">🏗️ Эффективность кладовщиков</div>
            <div style="overflow-x:auto">
                <table class="data-table">
                    <thead><tr>
                        <th>#</th>
                        <th>ФИО</th>
                        <th>Всего коробок</th>
                        <th>Скорость (кор/час)</th>
                        <th>Время (часов)</th>
                        <th>Действий</th>
                    </tr></thead>
                    <tbody>
                        ${data.map((r, i) => `
                            <tr>
                                <td style="font-weight:700;color:${i < 3 ? '#38bdf8' : 'var(--text-muted)'}">${i + 1}</td>
                                <td style="font-weight:600">${r.full_name}</td>
                                <td style="font-weight:700">${r.total_boxes}</td>
                                <td>
                                    <span style="font-weight:800;font-size:1.1rem;color:${r.speed_per_hour > 0 ? '#38bdf8' : 'var(--text-muted)'}">${r.speed_per_hour}</span>
                                    <span style="font-size:0.7rem;color:var(--text-muted)"> кор/ч</span>
                                </td>
                                <td style="color:var(--text-muted)">${r.total_hours}</td>
                                <td style="color:var(--text-muted)">${r.total_actions}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

/* ===================== My Shipments ===================== */
async function loadMyShipments() {
    const container = document.getElementById('shipments-list');
    container.innerHTML = '<div class="skeleton" style="height:60px;margin-bottom:8px"></div>'.repeat(3);

    const data = await API.get('/api/shipments?status_filter=active,completed');
    if (!data) return;

    if (data.length === 0) {
        container.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:32px">Нет активных поставок</p>';
        return;
    }

    container.innerHTML = data.map(s => `
        <div class="section-card" style="margin-bottom:12px;padding:16px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                <span style="font-weight:700">#${s.id} — ${s.name}</span>
                <span class="badge badge-${s.status}">${s.status === 'completed' ? '✅ Собрана' : '🟢 Активна'}</span>
            </div>
            <div style="display:flex;gap:16px;font-size:0.85rem;color:var(--text-muted);margin-bottom:12px">
                <span>📊 ${s.total_packed} / ${s.total_plan}</span>
                <span>📦 Коробов: ${s.box_count}</span>
                <span>📅 ${s.created_at || '—'}</span>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
                <button onclick="downloadShipmentReport(${s.id}, '${s.name}')" class="text-sm px-3 py-1.5 rounded-lg bg-blue-900/30 hover:bg-blue-900/50 text-blue-400 transition font-medium">📊 Отчёт</button>
                <button onclick="showAddItemsModal(${s.id}, '${s.name}')" class="text-sm px-3 py-1.5 rounded-lg bg-emerald-900/30 hover:bg-emerald-900/50 text-emerald-400 transition font-medium" data-roles="admin,manager">➕ Добавить товар</button>
                <button onclick="archiveShipment(${s.id})" class="text-sm px-3 py-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 transition font-medium">📂 В архив</button>
                ${['admin','manager'].includes(currentUser.role) ? `<button onclick="deleteShipment(${s.id})" class="text-sm px-3 py-1.5 rounded-lg bg-red-900/30 hover:bg-red-900/50 text-red-400 transition font-medium">🗑 Удалить</button>` : ''}
            </div>
        </div>
    `).join('');
}

async function archiveShipment(id) {
    if (!confirm('Переместить поставку в архив?')) return;
    const res = await API.post(`/api/shipments/${id}/archive`);
    if (res?.status === 'ok') { showToast('Поставка перемещена в архив'); loadMyShipments(); }
    else showToast(res?.detail || 'Ошибка', 'error');
}

async function deleteShipment(id) {
    if (!confirm('Удалить поставку? Это действие необратимо!')) return;
    const res = await API.del(`/api/shipments/${id}`);
    if (res?.status === 'ok') { showToast('Поставка удалена'); loadMyShipments(); }
    else showToast(res?.detail || 'Ошибка', 'error');
}

function downloadShipmentReport(id, name) {
    API.download(`/api/shipments/${id}/export-report`);
}

/* ---- Add Items to Shipment ---- */
let addItemsShipmentId = null;

function showAddItemsModal(id, name) {
    addItemsShipmentId = id;
    document.getElementById('add-items-modal-title').textContent = `➕ Добавить товар в: ${name} (#${id})`;
    document.getElementById('add-items-file').value = '';
    document.getElementById('add-items-info').textContent = '';
    document.getElementById('add-items-modal').classList.add('visible');
}

function closeAddItemsModal() {
    document.getElementById('add-items-modal').classList.remove('visible');
    addItemsShipmentId = null;
}

async function submitAddItems() {
    const fileInput = document.getElementById('add-items-file');
    const btn = document.getElementById('add-items-btn');

    if (!addItemsShipmentId) {
        showToast('Ошибка: не выбрана поставка', 'error');
        return;
    }
    if (!fileInput.files.length) {
        showToast('Выберите Excel файл', 'error');
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Загрузка...';

    const res = await API.postFile(`/api/shipments/${addItemsShipmentId}/add-items`, fileInput.files[0]);

    btn.disabled = false;
    btn.textContent = 'Загрузить';

    if (res?.status === 'ok') {
        showToast(`✅ Добавлено: ${res.total_articles} артикулов, ${res.added_qty} ед. (новых: ${res.new_articles})`);
        closeAddItemsModal();
        loadMyShipments();
    } else {
        showToast(res?.detail || 'Ошибка загрузки', 'error');
    }
}

/* ===================== My Receptions ===================== */
async function loadMyReceptions() {
    const container = document.getElementById('receptions-list');
    container.innerHTML = '<div class="skeleton" style="height:60px;margin-bottom:8px"></div>'.repeat(3);

    const data = await API.get('/api/receptions?status_filter=active,completed');
    if (!data) return;

    if (data.length === 0) {
        container.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:32px">Нет активных приёмок</p>';
        return;
    }

    container.innerHTML = data.map(s => `
        <div class="section-card" style="margin-bottom:12px;padding:16px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                <span style="font-weight:700">#${s.id} — ${s.name}</span>
                <span class="badge badge-active">🟢 Активна</span>
            </div>
            <div style="display:flex;gap:16px;font-size:0.85rem;color:var(--text-muted);margin-bottom:12px">
                <span>📊 Всего: ${s.total_scanned} ед.</span>
                <span>📅 ${s.created_at || '—'}</span>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
                <button onclick="downloadReceptionReport(${s.id}, '${s.name}')" class="text-sm px-3 py-1.5 rounded-lg bg-blue-900/30 hover:bg-blue-900/50 text-blue-400 transition font-medium">📥 Скан-Отчёт</button>
                <button onclick="downloadReceptionPackingReport(${s.id}, '${s.name}')" class="text-sm px-3 py-1.5 rounded-lg bg-purple-900/30 hover:bg-purple-900/50 text-purple-400 transition font-medium">📦 KPI Упаковки</button>
                <button onclick="completeReception(${s.id})" class="text-sm px-3 py-1.5 rounded-lg bg-green-900/30 hover:bg-green-900/50 text-green-400 transition font-medium">✅ Завершить</button>
                ${['admin','manager'].includes(currentUser.role) ? `<button onclick="deleteReception(${s.id})" class="text-sm px-3 py-1.5 rounded-lg bg-red-900/30 hover:bg-red-900/50 text-red-400 transition font-medium">🗑 Удалить</button>` : ''}
            </div>
        </div>
    `).join('');
}

async function completeReception(id) {
    if (!confirm('Завершить приёмку и обновить остатки?')) return;
    const res = await API.post(`/api/receptions/${id}/complete`);
    if (res?.status === 'ok') { showToast('Приёмка завершена, остатки обновлены'); loadMyReceptions(); }
    else showToast(res?.detail || 'Ошибка', 'error');
}

async function deleteReception(id) {
    if (!confirm('Удалить приёмку?')) return;
    const res = await API.del(`/api/receptions/${id}`);
    if (res?.status === 'ok') { showToast('Приёмка удалена'); loadMyReceptions(); }
    else showToast(res?.detail || 'Ошибка', 'error');
}

function downloadReceptionReport(id, name) {
    API.download(`/api/receptions/${id}/export-report`, `Скан_Приемка_${id}.xlsx`);
}

function downloadReceptionPackingReport(id, name) {
    API.download(`/api/receptions/${id}/export-packing-report`, `Упаковка_Приемка_${id}.xlsx`);
}

/* ===================== Excel Upload ===================== */
function showUploadModal(type) {
    const modal = document.getElementById('upload-modal');
    const title = document.getElementById('upload-modal-title');
    const form = document.getElementById('upload-form');

    title.textContent = type === 'shipment' ? '📦 Создать поставку из Excel' : '📥 Создать приёмку из Excel';
    form.dataset.type = type;
    document.getElementById('upload-file').value = '';
    document.getElementById('upload-info').innerHTML = '';
    modal.classList.add('visible');
}

function closeUploadModal() {
    document.getElementById('upload-modal').classList.remove('visible');
}

function onUploadFileSelected(input) {
    const name = input.files[0]?.name || '';
    document.getElementById('upload-info').textContent = name;
}

async function submitUpload() {
    const form = document.getElementById('upload-form');
    const fileInput = document.getElementById('upload-file');
    const type = form.dataset.type;
    const btn = document.getElementById('upload-btn');

    if (!fileInput.files.length) {
        showToast('Выберите Excel файл', 'error');
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Загрузка...';

    const url = type === 'shipment' ? '/api/shipments/upload' : '/api/receptions/upload';
    const res = await API.postFile(url, fileInput.files[0]);

    btn.disabled = false;
    btn.textContent = 'Загрузить';

    if (res?.status === 'ok') {
        showToast(`✅ ${type === 'shipment' ? 'Поставка' : 'Приёмка'} #${res.id} создана! Артикулов: ${res.articles}, Единиц: ${res.total}`);
        closeUploadModal();
    } else {
        showToast(res?.detail || 'Ошибка загрузки', 'error');
    }
}

/* ===================== Drag & Drop ===================== */
function initDragDrop() {
    const zones = document.querySelectorAll('.file-drop-zone');
    zones.forEach(zone => {
        zone.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.add('dragover');
        });

        zone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.remove('dragover');
        });

        zone.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.remove('dragover');

            const files = e.dataTransfer.files;
            if (files.length === 0) return;

            const file = files[0];
            if (!file.name.toLowerCase().endsWith('.xlsx')) {
                showToast('Нужен файл формата .xlsx', 'error');
                return;
            }

            // Find the hidden file input inside this zone
            const fileInput = zone.querySelector('input[type="file"]');
            if (fileInput) {
                // Create a DataTransfer to set files on input
                const dt = new DataTransfer();
                dt.items.add(file);
                fileInput.files = dt.files;

                // Trigger change event
                fileInput.dispatchEvent(new Event('change'));

                // Update info text
                const infoId = fileInput.id === 'upload-file' ? 'upload-info' :
                               fileInput.id === 'add-items-file' ? 'add-items-info' : null;
                if (infoId) {
                    document.getElementById(infoId).textContent = file.name;
                }
            }
        });
    });
}

/* ===================== Stock ===================== */
let stockShowArchived = false;

async function loadStock() {
    const container = document.getElementById('stock-list');
    container.innerHTML = '<div class="skeleton" style="height:60px;margin-bottom:8px"></div>'.repeat(3);

    const data = await API.get(`/api/stock?show_archived=${stockShowArchived}`);
    if (!data) return;

    if (data.length === 0) {
        container.innerHTML = `<p style="color:var(--text-muted);text-align:center;padding:32px">${stockShowArchived ? 'Архив пуст' : 'Склад пуст. Данные появятся после завершения приёмки.'}</p>`;
        return;
    }

    container.innerHTML = `
        <table class="data-table">
            <thead><tr>
                <th>Поставщик</th>
                <th>Позиций</th>
                <th>Остаток</th>
                <th>Обновлено</th>
                <th>Действия</th>
            </tr></thead>
            <tbody>
                ${data.map(s => `
                    <tr>
                        <td style="font-weight:600">${s.supplier_name}</td>
                        <td>${s.positions}</td>
                        <td><span style="font-weight:700;color:var(--accent)">${s.total}</span> ед.</td>
                        <td style="color:var(--text-muted);font-size:0.8rem">${s.updated_at || '—'}</td>
                        <td>
                            <div style="display:flex;gap:6px;flex-wrap:wrap">
                                <button onclick="downloadStockReport('${s.supplier_name}')" class="text-xs px-2 py-1 rounded bg-blue-900/30 hover:bg-blue-900/50 text-blue-400 transition">📊 Отчёт</button>
                                ${stockShowArchived
                                    ? `<button onclick="unarchiveSupplier('${s.supplier_name}')" class="text-xs px-2 py-1 rounded bg-green-900/30 hover:bg-green-900/50 text-green-400 transition">🔄 Вернуть</button>`
                                    : `<button onclick="archiveSupplier('${s.supplier_name}')" class="text-xs px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 transition">📂 Архив</button>`
                                }
                                ${currentUser.role === 'admin' ? `<button onclick="deleteSupplier('${s.supplier_name}')" class="text-xs px-2 py-1 rounded bg-red-900/30 hover:bg-red-900/50 text-red-400 transition">🗑</button>` : ''}
                            </div>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function toggleStockArchive() {
    stockShowArchived = !stockShowArchived;
    const btn = document.getElementById('stock-archive-toggle');
    btn.textContent = stockShowArchived ? '📦 Активные' : '📂 Архив';
    loadStock();
}

function downloadStockReport(supplier) {
    API.download(`/api/stock/${encodeURIComponent(supplier)}/report`, `stock_${supplier}.xlsx`);
}

async function archiveSupplier(name) {
    if (!confirm(`Архивировать поставщика «${name}»?`)) return;
    const res = await API.post(`/api/stock/${encodeURIComponent(name)}/archive`);
    if (res?.status === 'ok') { showToast('Поставщик в архиве'); loadStock(); }
    else showToast(res?.detail || 'Ошибка', 'error');
}

async function unarchiveSupplier(name) {
    const res = await API.post(`/api/stock/${encodeURIComponent(name)}/unarchive`);
    if (res?.status === 'ok') { showToast('Поставщик возвращён'); loadStock(); }
    else showToast(res?.detail || 'Ошибка', 'error');
}

async function deleteSupplier(name) {
    if (!confirm(`Удалить все данные поставщика «${name}»?`)) return;
    const res = await API.del(`/api/stock/${encodeURIComponent(name)}`);
    if (res?.status === 'ok') { showToast('Поставщик удалён'); loadStock(); }
    else showToast(res?.detail || 'Ошибка', 'error');
}

/* ===================== History ===================== */
let historyTab = 'shipments';

async function loadHistory() {
    await loadHistoryTab(historyTab);
}

function switchHistoryTab(tab) {
    historyTab = tab;
    document.getElementById('history-tab-shipments').classList.toggle('active', tab === 'shipments');
    document.getElementById('history-tab-receptions').classList.toggle('active', tab === 'receptions');
    loadHistoryTab(tab);
}

async function loadHistoryTab(tab) {
    const container = document.getElementById('history-list');
    container.innerHTML = '<div class="skeleton" style="height:40px;margin-bottom:8px"></div>'.repeat(4);

    const data = await API.get(`/api/history/${tab}`);
    if (!data) return;

    if (data.length === 0) {
        container.innerHTML = `<p style="color:var(--text-muted);text-align:center;padding:32px">Архив ${tab === 'shipments' ? 'поставок' : 'приёмок'} пуст</p>`;
        return;
    }

    container.innerHTML = `
        <table class="data-table">
            <thead><tr>
                <th>#</th>
                <th>Название</th>
                <th>Дата</th>
                <th>Действия</th>
            </tr></thead>
            <tbody>
                ${data.map(s => `
                    <tr>
                        <td style="font-weight:600;color:var(--accent)">${s.id}</td>
                        <td>${s.name}</td>
                        <td style="color:var(--text-muted)">${s.created_at}</td>
                        <td>
                            <div style="display:flex;gap:6px">
                                <button onclick="${tab === 'shipments' ? 'downloadShipmentReport' : 'downloadReceptionReport'}(${s.id}, '${s.name.replace(/'/g, "\\'")}')" class="text-xs px-2 py-1 rounded bg-blue-900/30 hover:bg-blue-900/50 text-blue-400 transition">📥 Скан-Отчёт</button>
                                ${tab === 'receptions' ? `<button onclick="downloadReceptionPackingReport(${s.id}, '${s.name.replace(/'/g, "\\'")}')" class="text-xs px-2 py-1 rounded bg-purple-900/30 hover:bg-purple-900/50 text-purple-400 transition">📦 Отчёт KPI</button>` : ''}
                                ${['admin', 'manager'].includes(currentUser.role) ? `<button onclick="reopenItem(${s.id})" class="text-xs px-2 py-1 rounded bg-yellow-900/30 hover:bg-yellow-900/50 text-yellow-400 transition">🔄 Вернуть</button>` : ''}
                            </div>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

async function reopenItem(id) {
    if (!confirm('Вернуть из архива?')) return;
    const res = await API.post(`/api/history/${id}/reopen`);
    if (res?.status === 'ok') { showToast('Возвращено из архива'); loadHistory(); }
    else showToast(res?.detail || 'Ошибка', 'error');
}

/* ===================== Users ===================== */
async function loadUsers() {
    const container = document.getElementById('users-list');
    container.innerHTML = '<div class="skeleton" style="height:40px;margin-bottom:8px"></div>'.repeat(3);

    const data = await API.get('/api/users');
    if (!data) return;

    container.innerHTML = `
        <table class="data-table">
            <thead><tr>
                <th>Логин</th>
                <th>ФИО</th>
                <th>Роль</th>
                <th>Дата создания</th>
                ${['admin','manager'].includes(currentUser.role) ? '<th>Действия</th>' : ''}
            </tr></thead>
            <tbody>
                ${data.map(u => `
                    <tr>
                        <td style="font-weight:600">${u.username}</td>
                        <td style="color:${u.full_name ? 'var(--text-primary)' : 'var(--text-muted)'}">${u.full_name || '—'}</td>
                        <td>${getRoleBadge(u.role)}</td>
                        <td style="color:var(--text-muted);font-size:0.85rem">${u.created_at || '—'}</td>
                        ${['admin','manager'].includes(currentUser.role) ? `
                            <td>
                                ${u.username !== currentUser.username ? `<button onclick="deleteUser(${u.id}, '${u.username}')" class="text-xs px-2 py-1 rounded bg-red-900/30 hover:bg-red-900/50 text-red-400 transition">🗑 Удалить</button>` : '<span style="color:var(--text-muted);font-size:0.8rem">Вы</span>'}
                            </td>
                        ` : ''}
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function showCreateUserModal() {
    document.getElementById('create-user-modal').classList.add('visible');
    document.getElementById('new-username').value = '';
    document.getElementById('new-fullname').value = '';
    document.getElementById('new-password').value = '';

    // Role options based on current user role
    const roleSelect = document.getElementById('new-role');
    roleSelect.innerHTML = '';
    if (currentUser.role === 'admin') {
        roleSelect.innerHTML += '<option value="manager">Менеджер</option>';
    }
    roleSelect.innerHTML += '<option value="packer">Упаковщица</option>';
    roleSelect.innerHTML += '<option value="warehouseman">Кладовщик</option>';
}

function closeCreateUserModal() {
    document.getElementById('create-user-modal').classList.remove('visible');
}

async function createUser() {
    const username = document.getElementById('new-username').value.trim();
    const full_name = document.getElementById('new-fullname').value.trim();
    const password = document.getElementById('new-password').value;
    const role = document.getElementById('new-role').value;

    if (!username || !password) {
        showToast('Заполните логин и пароль', 'error');
        return;
    }

    const body = { username, password, role };
    if (full_name) body.full_name = full_name;

    const res = await API.post('/api/users', body);
    if (res?.id) {
        showToast(`Пользователь ${full_name || username} создан`);
        closeCreateUserModal();
        loadUsers();
    } else {
        showToast(res?.detail || 'Ошибка создания', 'error');
    }
}

async function deleteUser(id, username) {
    if (!confirm(`Удалить пользователя ${username}?`)) return;
    const res = await API.del(`/api/users/${id}`);
    if (res?.status === 'ok') { showToast(`Пользователь ${username} удалён`); loadUsers(); }
    else showToast(res?.detail || 'Ошибка', 'error');
}
