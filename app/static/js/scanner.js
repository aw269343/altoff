/**
 * scanner.js — html5-qrcode barcode scanner for reception, shipment, and pack modes
 * Turbo mode: CODE_128 + EAN_13, fps 20, rear camera, rectangle qrbox
 */

let scannerState = {
    mode: 'shipment',   // 'reception' | 'shipment' | 'pack'
    shipmentId: null,
    receptionId: null,
    boxNumber: null,
    isProcessing: false,
    scanCooldown: false,
    scannerRunning: false,
    lastScannedBarcode: '',
    torchOn: false,
    audioCtx: null,
    // Packing flow state
    packStartTime: null,       // ISO string of when OK was pressed
    currentItem: null,         // current item data from ТЗ
    totalPlan: 0,
    totalPacked: 0,
};

document.addEventListener('DOMContentLoaded', () => {
    if (!API.getToken()) { window.location.href = '/'; return; }

    if (location.protocol !== 'https:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
        document.getElementById('https-warning').style.display = 'block';
    }

    const params = new URLSearchParams(window.location.search);
    scannerState.mode = params.get('mode') || 'shipment';

    if (scannerState.mode === 'reception') {
        initReceptionMode();
    } else if (scannerState.mode === 'global_pack') {
        initGlobalPackMode();
    } else {
        initShipmentMode(); // default assembly
    }
});

/* ===================== Audio ===================== */
function getAudioCtx() {
    if (!scannerState.audioCtx) {
        scannerState.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    return scannerState.audioCtx;
}

function playBeep() {
    try {
        const c = getAudioCtx(), o = c.createOscillator(), g = c.createGain();
        o.type = 'sine'; o.frequency.setValueAtTime(1760, c.currentTime);
        g.gain.setValueAtTime(0.25, c.currentTime);
        g.gain.exponentialRampToValueAtTime(0.01, c.currentTime + 0.08);
        o.connect(g); g.connect(c.destination);
        o.start(c.currentTime); o.stop(c.currentTime + 0.08);
    } catch (e) { }
}

function playSuccessSound() {
    try {
        const c = getAudioCtx(), o = c.createOscillator(), g = c.createGain();
        o.type = 'sine';
        o.frequency.setValueAtTime(880, c.currentTime);
        o.frequency.setValueAtTime(1174.66, c.currentTime + 0.1);
        g.gain.setValueAtTime(0.35, c.currentTime);
        g.gain.exponentialRampToValueAtTime(0.01, c.currentTime + 0.25);
        o.connect(g); g.connect(c.destination);
        o.start(c.currentTime); o.stop(c.currentTime + 0.25);
    } catch (e) { }
}

function playErrorSound() {
    try {
        const c = getAudioCtx(), o = c.createOscillator(), g = c.createGain();
        o.type = 'square';
        o.frequency.setValueAtTime(200, c.currentTime);
        o.frequency.setValueAtTime(150, c.currentTime + 0.15);
        o.frequency.setValueAtTime(100, c.currentTime + 0.3);
        g.gain.setValueAtTime(0.4, c.currentTime);
        g.gain.exponentialRampToValueAtTime(0.01, c.currentTime + 0.5);
        o.connect(g); g.connect(c.destination);
        o.start(c.currentTime); o.stop(c.currentTime + 0.5);
    } catch (e) { }
}

function vibrate(pattern) {
    try { if (navigator.vibrate) navigator.vibrate(pattern); } catch (e) { }
}

/* ===================== Html5Qrcode Scanner ===================== */
let html5QrcodeScanner = null;

function startScanner(targetId) {
    if (scannerState.scannerRunning) return;
    const target = targetId || 'reader';

    html5QrcodeScanner = new Html5Qrcode(target);
    const config = {
        fps: 20,
        qrbox: { width: 280, height: 100 },
        formatsToSupport: [
            Html5QrcodeSupportedFormats.CODE_128,
            Html5QrcodeSupportedFormats.EAN_13,
        ],
    };

    html5QrcodeScanner.start(
        { facingMode: "environment" },
        config,
        (decodedText, decodedResult) => {
            if (scannerState.isProcessing || scannerState.scanCooldown) return;
            const code = decodedText;
            if (!code || code.length < 4) return;

            scannerState.scanCooldown = true;
            setTimeout(() => { scannerState.scanCooldown = false; }, 1500);

            playBeep();
            vibrate(50);

            if (scannerState.mode === 'reception') {
                onReceptionScanned(code);
            } else if (scannerState.mode === 'global_pack') {
                onPackScanned(code);
            } else {
                onShipmentScanned(code);
            }
        },
        (errorMessage) => {
            // parse errors are ignored
        }
    ).then(() => {
        scannerState.scannerRunning = true;
    }).catch((err) => {
        console.warn('Html5Qrcode init error:', err);
        document.getElementById(target).innerHTML =
            '<div style="padding:24px;text-align:center;color:var(--text-muted)">' +
            '<p style="font-size:1.1rem;margin-bottom:8px">📷 Камера недоступна</p>' +
            '<p>Используйте поле ввода ниже</p></div>';
    });
}

function stopScanner() {
    if (html5QrcodeScanner && scannerState.scannerRunning) {
        html5QrcodeScanner.stop().then(() => {
            scannerState.scannerRunning = false;
        }).catch((err) => console.error("Failed to stop scanner", err));
    }
}

/* ===================== Torch ===================== */
function toggleTorch() {
    if (!html5QrcodeScanner) return;
    try {
        scannerState.torchOn = !scannerState.torchOn;
        html5QrcodeScanner.applyVideoConstraints({ advanced: [{ torch: scannerState.torchOn }] });
        const btn = document.getElementById('btn-torch');
        btn.classList.toggle('active', scannerState.torchOn);
        btn.textContent = scannerState.torchOn ? '🔦 Фонарик ВКЛ' : '🔦 Фонарик';
    } catch (e) {
        console.warn('Torch not supported:', e);
    }
}

/* ===================== Flash ===================== */
function showFlash(type, msg) {
    const ov = document.getElementById('scanner-flash');
    document.getElementById('flash-icon').textContent = type === 'success' ? '✓' : '✕';
    document.getElementById('flash-text').textContent = msg;
    ov.className = 'scanner-flash ' + type;
    ov.style.display = 'flex';
    if (type === 'success') setTimeout(dismissFlash, 1000);
}

function dismissFlash() {
    const ov = document.getElementById('scanner-flash');
    ov.style.display = 'none';
    scannerState.isProcessing = false;
}

function updateProgressBar(packed, total) {
    scannerState.totalPacked = packed;
    scannerState.totalPlan = total;
    const container = document.getElementById('packing-progress');
    if (!container) return;
    const pct = total > 0 ? Math.min(100, Math.round((packed / total) * 100)) : 0;
    container.innerHTML = `
        <div class="progress-text">
            <span class="progress-label">📦 Общий прогресс</span>
            <span class="progress-value">${packed} из ${total} (${pct}%)</span>
        </div>
        <div class="progress-bar-wrapper">
            <div class="progress-bar-fill" style="width:${pct}%"></div>
        </div>
    `;
    container.style.display = 'block';
}

function updateBoxDisplay() {
    let el = document.getElementById('box-num-val');
    if (el) el.textContent = scannerState.boxNumber || '—';
    el = document.getElementById('box-num-val-pack');
    if (el) el.textContent = scannerState.boxNumber || '—';
}

/* ===================== COMMON SHIPMENT LIST ===================== */
async function loadShipmentsList() {
    const data = await API.get('/api/shipments?status_filter=active');
    const sel = document.getElementById('shipment-select');
    sel.innerHTML = '';
    if (!data || !data.length) {
        sel.innerHTML = '<option value="">Нет активных поставок</option>';
        return;
    }
    data.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = `#${s.id} — ${s.name}`;
        sel.appendChild(opt);
    });
    document.getElementById('btn-start-shipment').disabled = false;
}

async function startCommonShipmentWork(setupControlsId) {
    const sel = document.getElementById('shipment-select');
    if (!sel.value) return;
    scannerState.shipmentId = parseInt(sel.value);

    const res = await API.post(`/api/shipments/${scannerState.shipmentId}/open-box`);
    if (res?.status === 'ok') {
        scannerState.boxNumber = res.box_number;
        updateBoxDisplay();
    }

    document.getElementById('shipment-setup').style.display = 'none';
    document.getElementById('scanner-work').style.display = 'block';
    document.getElementById('reception-controls').style.display = 'none';
    
    // Hide both, show the right one
    document.getElementById('shipment-controls').style.display = 'none';
    document.getElementById('pack-controls').style.display = 'none';
    document.getElementById(setupControlsId).style.display = 'block';

    loadShipmentProgress();
    startScanner('reader');
}

/* ===================== SHIPMENT MODE (ASSEMBLY) ===================== */
async function initShipmentMode() {
    document.getElementById('scanner-title').textContent = '🛠️ Сборка поставки';
    document.getElementById('shipment-setup').style.display = 'block';
    document.getElementById('reception-setup').style.display = 'none';
    loadShipmentsList();
}

function startShipmentWork() {
    startCommonShipmentWork(scannerState.mode === 'pack' ? 'pack-controls' : 'shipment-controls');
}

async function onShipmentScanned(code) {
    if (scannerState.isProcessing) return;
    scannerState.isProcessing = true;
    const barcode = code.trim();
    scannerState.lastScannedBarcode = barcode;
    document.getElementById('last-barcode-display').textContent = 'ШК: ' + barcode;

    const qtyEl = document.getElementById('scan-qty');
    let qty = parseInt(qtyEl ? qtyEl.value : '1');
    if (!qty || qty < 1) qty = 1;

    try {
        const res = await API.post(`/api/shipments/${scannerState.shipmentId}/scan`, {
            item_barcode: barcode,
            quantity: qty,
            box_number: scannerState.boxNumber,
        });

        if (res?.status === 'ok') {
            playSuccessSound(); vibrate(80);
            if (qtyEl) { qtyEl.value = '1'; qtyEl.blur(); }
            showFlash('success', '✅ ' + barcode + ' x' + qty);
            loadShipmentProgress();
        } else {
            playErrorSound(); vibrate([200, 100, 200, 100, 300]);
            showFlash('error', res?.detail || 'Ошибка');
        }
    } catch (e) {
        playErrorSound(); vibrate([200, 100, 200]);
        showFlash('error', 'Ошибка связи');
    } finally {
        scannerState.isProcessing = false;
    }
}

function submitShipmentScan() {
    if (!scannerState.lastScannedBarcode) {
        showFlash('error', 'Сначала отсканируйте штрихкод');
        return;
    }
    onShipmentScanned(scannerState.lastScannedBarcode);
}

async function initGlobalPackMode() {
    document.getElementById('scanner-title').textContent = '📦 Глобальная Упаковка';
    document.getElementById('shipment-setup').style.display = 'none';
    document.getElementById('reception-setup').style.display = 'none';

    // Jump straight to scanner — no setup needed
    document.getElementById('scanner-work').style.display = 'block';
    document.getElementById('shipment-controls').style.display = 'none';
    document.getElementById('reception-controls').style.display = 'none';
    document.getElementById('pack-controls').style.display = 'block';

    // Hide progress table — packers only see the progress bar
    const progressCard = document.querySelector('#scanner-work .section-card');
    if (progressCard) progressCard.style.display = 'none';

    startScanner('reader');
}

async function onPackScanned(code) {
    if (scannerState.isProcessing || document.getElementById('pack-modal').style.display === 'flex') return;
    scannerState.isProcessing = true;
    const barcode = code.trim();
    scannerState.lastScannedBarcode = barcode;
    document.getElementById('last-barcode-display').textContent = 'ШК: ' + barcode;

    try {
        const taskData = await API.get(`/api/receptions/global-task/${barcode}`);
        if (!taskData) {
            scannerState.isProcessing = false;
            return;
        }

        scannerState.currentItem = taskData;
        showPackModal(taskData);
        updateProgressBar(taskData.total_packed, taskData.total_plan);

        playBeep();
    } catch (e) {
        playErrorSound(); vibrate([200, 100, 200]);
        // showFlash('error', 'Ошибка связи'); (already handled by API.get)
    } finally {
        scannerState.isProcessing = false;
    }
}

function showPackModal(item) {
    const remaining = Math.max(0, item.remaining_to_pack);
    const isComplete = remaining <= 0;
    const tzNames = item.technical_assignments.join(', ') || 'Без ТЗ';

    const tzModalContent = document.getElementById('pack-modal-tz');
    tzModalContent.innerHTML = `
        <div class="tz-barcode">${item.barcode}</div>
        <div class="tz-info">
            <span>Артикул:</span> <strong>${item.article}</strong>
            <span>Размер:</span> <strong>${item.size}</strong>
            <span>ТЗ:</span> <strong>${tzNames}</strong>
            <span>План:</span> <strong>${item.total_plan} шт.</strong>
            <span>Упаковано:</span> <strong style="color:${isComplete ? 'var(--success)' : 'var(--accent)'}">${item.total_packed} шт.</strong>
            <span>Осталось:</span> <strong style="color:${isComplete ? 'var(--success)' : remaining < 5 ? 'var(--warning)' : 'var(--text-primary)'}">${isComplete ? '✅ Готово' : remaining + ' шт.'}</strong>
        </div>
    `;

    // Pause image scanning to prevent background scans while modal is up
    if (html5QrcodeScanner && scannerState.scannerRunning) {
        html5QrcodeScanner.pause();
    }

    document.getElementById('pack-step-1').style.display = 'block';
    document.getElementById('pack-step-2').style.display = 'none';
    document.getElementById('pack-modal').style.display = 'flex';
}

function cancelPackModal() {
    document.getElementById('pack-modal').style.display = 'none';
    scannerState.packStartTime = null;
    document.getElementById('pack-quantity').value = '1';
    
    // Resume scanning
    if (html5QrcodeScanner && scannerState.scannerRunning) {
        html5QrcodeScanner.resume();
    }
}

function startPackTimer() {
    scannerState.packStartTime = new Date().toISOString();
    document.getElementById('pack-step-1').style.display = 'none';
    document.getElementById('pack-step-2').style.display = 'block';
    const qtyEl = document.getElementById('pack-quantity');
    if (qtyEl) { qtyEl.focus(); qtyEl.select(); }
}

async function submitGlobalPack() {
    const barcode = scannerState.lastScannedBarcode;
    if (!barcode) return;

    if (scannerState.isProcessing) return;
    scannerState.isProcessing = true;

    const qtyEl = document.getElementById('pack-quantity');
    let qty = parseInt(qtyEl ? qtyEl.value : '1');
    if (!qty || qty < 1) qty = 1;

    if (!scannerState.packStartTime) {
        scannerState.packStartTime = new Date().toISOString();
    }

    try {
        const res = await API.post(`/api/receptions/global-pack`, {
            barcode: barcode,
            quantity: qty,
            start_time: scannerState.packStartTime,
            // box_number is intentionally omitted
        });

        if (res?.status === 'ok') {
            playSuccessSound(); vibrate(80);
            
            let flashMsg = '✅ ' + barcode + (qty > 1 ? ' x' + qty : '') + '\n' + res.progress;
            if (res.is_error) { flashMsg = '⚠️ ПЕРЕБОР! ' + barcode + '\n' + res.progress; }
            showFlash(res.is_error ? 'error' : 'success', flashMsg);

            updateProgressBar(res.total_packed, res.total_plan);
            cancelPackModal(); // closes and resets logic
        } else {
            playErrorSound(); vibrate([200, 100, 200, 100, 300]);
            showFlash('error', res?.detail || res?.message || 'Ошибка');
        }
    } catch (e) {
        playErrorSound(); vibrate([200, 100, 200]);
        showFlash('error', 'Ошибка сервера');
    } finally {
        scannerState.isProcessing = false;
    }
}

/* ===================== COMMON SHIPMENT HELPERS ===================== */
async function loadShipmentProgress() {
    if (!scannerState.shipmentId) return;
    const data = await API.get(`/api/shipments/${scannerState.shipmentId}`);
    if (!data) return;

    if (scannerState.mode === 'pack') {
        updateProgressBar(data.total_packed, data.total_plan);
    } else {
        const container = document.getElementById('packing-progress');
        if (container) container.style.display = 'none';
        const tz = document.getElementById('tz-display');
        if (tz) tz.style.display = 'none';
    }

    const tb = document.getElementById('progress-body');
    tb.innerHTML = '';
    data.items.forEach(item => {
        const tr = document.createElement('tr');
        if (item.remaining <= 0 && item.packed <= item.quantity) tr.style.color = 'var(--success)';
        else if (item.packed > item.quantity) tr.style.color = 'var(--danger)';

        if (item.barcode === scannerState.lastScannedBarcode) {
            tr.style.background = 'rgba(59,130,246,0.08)';
            tr.style.fontWeight = '600';
        }
        tr.innerHTML = `<td>${item.barcode}</td><td>${item.article}</td><td style="text-align:center">${item.size}</td><td style="text-align:center">${item.quantity}</td><td style="text-align:center">${item.packed}</td><td style="text-align:center">${item.remaining > 0 ? item.remaining : '✓'}</td>`;
        tb.appendChild(tr);
    });
}

async function closeBox() {
    if (!scannerState.shipmentId || !confirm('Закрыть короб #' + scannerState.boxNumber + '?')) return;
    const res = await API.post(`/api/shipments/${scannerState.shipmentId}/close-box`);
    if (res?.status === 'ok') {
        playSuccessSound(); vibrate([100, 50, 100]);
        scannerState.boxNumber = res.box_number;
        updateBoxDisplay();
        if (res.completed) {
            stopScanner();
            showFlash('success', '🎉 Поставка полностью собрана!');
            setTimeout(() => { window.location.href = '/dashboard'; }, 2000);
        }
    } else {
        showFlash('error', res?.detail || 'Ошибка');
    }
}

/* ===================== RECEPTION MODE ===================== */
async function initReceptionMode() {
    document.getElementById('scanner-title').textContent = '📥 Приёмка товара';
    document.getElementById('shipment-setup').style.display = 'none';
    document.getElementById('reception-setup').style.display = 'block';
    loadReceptionsList();
}

async function loadReceptionsList() {
    const data = await API.get('/api/receptions?status_filter=active');
    const sel = document.getElementById('reception-select');
    sel.innerHTML = '';
    if (!data || !data.length) {
        sel.innerHTML = '<option value="">Нет активных приёмок</option>';
        document.getElementById('reception-list-card').style.display = 'none';
        return;
    }
    document.getElementById('reception-list-card').style.display = 'block';
    data.forEach(r => {
        const opt = document.createElement('option');
        opt.value = r.id;
        opt.textContent = `#${r.id} — ${r.name}`;
        sel.appendChild(opt);
    });
    document.getElementById('btn-continue-reception').disabled = false;
}

async function createNewReception() {
    const nameInput = document.getElementById('reception-name-input');
    const name = nameInput.value.trim();
    if (!name) { nameInput.focus(); return; }

    const res = await API.post('/api/receptions', { name });
    if (res?.status === 'ok') {
        scannerState.receptionId = res.id;
        document.getElementById('reception-name-display').textContent = name;
        startReceptionWork();
    } else {
        showFlash('error', res?.detail || 'Ошибка создания');
    }
}

function continueReception() {
    const sel = document.getElementById('reception-select');
    if (!sel.value) return;
    scannerState.receptionId = parseInt(sel.value);
    document.getElementById('reception-name-display').textContent = sel.options[sel.selectedIndex].textContent;
    startReceptionWork();
}

function startReceptionWork() {
    document.getElementById('reception-setup').style.display = 'none';
    document.getElementById('scanner-work').style.display = 'block';
    document.getElementById('shipment-controls').style.display = 'none';
    document.getElementById('pack-controls').style.display = 'none';
    document.getElementById('reception-controls').style.display = 'block';

    loadReceptionProgress();
    startScanner('reader');
}

async function onReceptionScanned(code) {
    if (scannerState.isProcessing) return;
    scannerState.isProcessing = true;
    const barcode = code.trim();
    scannerState.lastScannedBarcode = barcode;
    const qtyEl = document.getElementById('scan-qty-r');
    let qty = parseInt(qtyEl ? qtyEl.value : '1');
    if (!qty || qty < 1) qty = 1;

    try {
        const res = await API.post(`/api/receptions/${scannerState.receptionId}/scan`, {
            barcode, quantity: qty,
        });

        if (res?.status === 'ok') {
            playSuccessSound(); vibrate(80);
            if (qtyEl) { qtyEl.value = '1'; qtyEl.blur(); }
            showFlash('success', '✅ ' + barcode + (qty > 1 ? ' x' + qty : '') + '\nКол-во: ' + res.quantity);
            loadReceptionProgress();
        } else {
            playErrorSound(); vibrate([200, 100, 200, 100, 300]);
            showFlash('error', res?.detail || 'Ошибка');
        }
    } catch (e) {
        playErrorSound(); vibrate([200, 100, 200]);
        showFlash('error', 'Ошибка связи с сервером');
    } finally {
        scannerState.isProcessing = false;
    }
}

function manualScanSubmit() {
    const inp = document.getElementById('manual-barcode-input');
    const v = inp.value.trim();
    if (v) {
        if (scannerState.mode === 'reception') onReceptionScanned(v);
        else if (scannerState.mode === 'global_pack') onPackScanned(v);
        else onShipmentScanned(v);
        inp.value = '';
    }
}

async function loadReceptionProgress() {
    if (!scannerState.receptionId) return;
    const data = await API.get(`/api/receptions/${scannerState.receptionId}`);
    if (!data) return;

    const container = document.getElementById('packing-progress');
    if (container) container.style.display = 'none';
    const tz = document.getElementById('tz-display');
    if (tz) tz.style.display = 'none';

    const tb = document.getElementById('progress-body');
    tb.innerHTML = '';
    data.items.forEach(item => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${item.barcode}</td><td>${item.article}</td><td style="text-align:center">${item.size}</td><td style="text-align:center" colspan="3">${item.quantity}</td>`;
        tb.appendChild(tr);
    });
}

function goBack() {
    stopScanner();
    if (scannerState.mode === 'global_pack') {
        window.location.href = '/dashboard';
    } else if (scannerState.mode === 'reception') {
        document.getElementById('scanner-work').style.display = 'none';
        document.getElementById('reception-setup').style.display = 'block';
        loadReceptionsList();
    } else {
        document.getElementById('scanner-work').style.display = 'none';
        document.getElementById('shipment-setup').style.display = 'block';
    }
}

function goToDashboard() {
    stopScanner();
    window.location.href = '/dashboard';
}
