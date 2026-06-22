/**
 * GrantPulse — Frontend SPA v2
 * Radar de Financiamiento para Consultor
 * Vanilla JS · No framework · API-driven
 */

'use strict';

/* ─── CONSTANTS ──────────────────────────────────────────────── */
const API       = '/api/v1';
const PAGE_SIZE = 24;

/* ─── UTILS ──────────────────────────────────────────────────── */
const $  = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s ?? '';
  return d.innerHTML;
}

function fmt(n) {
  if (n == null) return '—';
  return new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP', maximumFractionDigits: 0 }).format(n);
}

function fmtDate(d) {
  if (!d) return '—';
  const date = new Date(d);
  if (isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('es-CL', { day: '2-digit', month: 'short', year: 'numeric' });
}

function fmtDateTime(d) {
  if (!d) return '—';
  const date = new Date(d);
  if (isNaN(date.getTime())) return '—';
  return date.toLocaleString('es-CL', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function fmtRelative(d) {
  if (!d) return 'Nunca';
  const diff = Date.now() - new Date(d).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Ahora mismo';
  if (mins < 60) return `hace ${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `hace ${hrs}h`;
  const days = Math.floor(hrs / 24);
  return `hace ${days}d`;
}

/**
 * Calcula días hasta cierre. null = sin fecha.
 * @param {string|null} fechaCierre
 * @returns {number|null}
 */
function diasHastaCierre(fechaCierre) {
  if (!fechaCierre) return null;
  const cierre = new Date(fechaCierre);
  if (isNaN(cierre.getTime())) return null;
  const diff = cierre.getTime() - Date.now();
  return Math.ceil(diff / 86400000);
}

/**
 * Retorna la clase de urgencia basada en días hasta cierre.
 */
function urgencyClass(dias) {
  if (dias === null) return 'urgency-none';
  if (dias <= 10)  return 'urgency-high';
  if (dias <= 30)  return 'urgency-mid';
  return 'urgency-low';
}

/**
 * Retorna chip HTML de urgencia.
 */
function urgencyChip(dias) {
  if (dias === null) return '<span class="urgency-chip none">Sin fecha</span>';
  if (dias < 0)     return '<span class="urgency-chip high">Vencida</span>';
  if (dias <= 10)   return `<span class="urgency-chip high">⚡ ${dias}d</span>`;
  if (dias <= 30)   return `<span class="urgency-chip mid">⏳ ${dias}d</span>`;
  return `<span class="urgency-chip low">${dias}d restantes</span>`;
}

function badgeClass(estado) {
  const e = (estado || '').toUpperCase();
  if (e.includes('ABIERT'))     return 'badge-green';
  if (e.includes('CERRAD') || e.includes('FINALIZAD') || e.includes('ADJUDICAD') || e.includes('SUSPENDID')) return 'badge-red';
  if (e.includes('PROXIM'))     return 'badge-amber';
  if (e.includes('PERMANENT'))  return 'badge-cyan';
  if (e.includes('DESCONOCID')) return 'badge-gray';
  return 'badge-cyan';
}

function institutionInitials(nombre) {
  if (!nombre) return '??';
  const words = nombre.trim().split(/\s+/);
  if (words.length === 1) return nombre.substring(0, 2).toUpperCase();
  return words.slice(0, 2).map(w => w[0]).join('').toUpperCase();
}

function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  $('#toastContainer').appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function showConfirm(title, msg, cb) {
  $('#confirmModalTitle').textContent = title;
  $('#confirmModalMsg').textContent = msg;
  state.confirmCb = cb;
  $('#confirmModal').classList.add('active');
}

/* ─── STATE ──────────────────────────────────────────────────── */
const state = {
  page:         'radar',
  fuentes:      [],
  convocatorias:[],
  selectedFuenteId: null,   // null = todas
  selectedFuenteNombre: null,
  convOffset:   0,
  convTotal:    0,
  searchTimeout: null,
  confirmCb:    null,
};

/* ─── API ────────────────────────────────────────────────────── */
async function apiFetch(path, opts = {}) {
  const r = await fetch(`${API}${path}`, opts);
  if (!r.ok) {
    const detail = r.status !== 204 ? await r.text().catch(() => '') : '';
    throw new Error(`${r.status}: ${detail}`);
  }
  if (r.status === 204) return null;
  return r.json();
}

/* ─── NAVIGATION ─────────────────────────────────────────────── */
function navigate(page) {
  state.page = page;
  $$('.page').forEach(p => p.classList.remove('active'));
  $(`#page-${page}`).classList.add('active');
  $$('.nav-item[data-page]').forEach(b => b.classList.toggle('active', b.dataset.page === page));
  loadPage(page);
}

function loadPage(page) {
  switch (page) {
    case 'radar':         loadRadar();         break;
    case 'instituciones': loadInstituciones(); break;
    case 'briefing':      loadBriefing();      break;
    case 'admin':         loadAdmin();         break;
    case 'suscripciones': loadSuscripciones(); break;
  }
}

/* ═══════════════════════════════════════════════════════════════
   RADAR ACTIVO
═══════════════════════════════════════════════════════════════ */

async function loadRadar() {
  const soloActivas = $('#soloActivasToggle').checked;
  const search      = $('#searchInput').value.trim();
  const orden       = $('#filterOrden').value;
  const region      = $('#filterRegion').value;

  showRadarLoading(true);

  try {
    // Parámetros para todas las llamadas
    const listParams = new URLSearchParams();
    listParams.set('limit',  PAGE_SIZE);
    listParams.set('offset', state.convOffset);
    if (soloActivas) listParams.set('estado', 'ABIERTO');
    if (state.selectedFuenteId) listParams.set('fuente_id', state.selectedFuenteId);
    if (search)  listParams.set('search', search);
    if (orden)   listParams.set('orden',  orden);
    if (region)  listParams.set('region', region);

    const filterParams = new URLSearchParams();
    if (soloActivas) filterParams.set('estado', 'ABIERTO');
    if (state.selectedFuenteId) filterParams.set('fuente_id', state.selectedFuenteId);
    if (region) filterParams.set('region', region);
    if (search) filterParams.set('search', search);

    // Llamadas en paralelo: datos, conteo, KPIs, y badge global
    const [data, countData, kpiData] = await Promise.all([
      apiFetch(`/convocatorias?${listParams}`),
      apiFetch(`/convocatorias/count?${filterParams}`),
      apiFetch(`/convocatorias/kpi?${filterParams}`),
    ]);

    state.convocatorias = data;
    state.convTotal = countData.total;

    renderConvGrid(data);
    updateResultPill(countData.total);
    renderConvPagination();
    updateActivePill(countData.total);

    // KPIs desde el endpoint dedicado
    $('#kpiAbiertas').textContent = kpiData.abiertas;
    $('#kpiVencen30').textContent = kpiData.vencen_30;
    $('#kpiInstituciones').textContent = kpiData.instituciones;
    $('#kpiSinFecha').textContent = kpiData.sin_fecha;

    // Badge global de navegación (total activas global, sin filtros)
    const globalCount = await apiFetch('/convocatorias/count?estado=ABIERTO');
    $('#navBadgeRadar').textContent = globalCount.total || '';

  } catch (e) {
    console.error('Radar error:', e);
    toast('Error al cargar convocatorias', 'error');
    showRadarEmpty(true);
  } finally {
    showRadarLoading(false);
  }
}

function showRadarLoading(show) {
  $('#radarLoader').style.display = show ? 'flex' : 'none';
  if (show) {
    $('#radarEmpty').style.display = 'none';
    $('#convGrid').innerHTML = '';
  }
}

function showRadarEmpty(show) {
  $('#radarEmpty').style.display = show ? 'flex' : 'none';
}

function updateActivePill(total) {
  const soloActivas = $('#soloActivasToggle').checked;
  const label = soloActivas ? `${total} activas` : `${total} convocatorias`;
  $('#activePillLabel').textContent = label;
}

function updateResultPill(total) {
  $('#resultNum').textContent = total;
}

/* ── RENDER CARDS ──────────────────────────────────────────────── */
function renderConvGrid(items) {
  const grid = $('#convGrid');

  if (!items.length) {
    grid.innerHTML = '';
    showRadarEmpty(true);
    return;
  }

  showRadarEmpty(false);
  grid.innerHTML = items.map(c => buildConvCard(c)).join('');
}

function buildConvCard(c) {
  const dias  = diasHastaCierre(c.fecha_cierre);
  const uCls  = urgencyClass(dias);
  const chip  = urgencyChip(dias);
  const initials = institutionInitials(c.fuente_nombre);

  const urlBtn = c.url_detalle
    ? `<a class="card-url-btn" href="${escHtml(c.url_detalle)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()" title="Ir a postulación oficial">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
        Postular / Ver bases
      </a>`
    : `<span class="card-url-btn disabled" title="URL no disponible">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
        Sin URL directa
      </span>`;

  return `
  <div class="conv-card ${uCls}" onclick="viewDetail('${c.id}')" tabindex="0" role="button" aria-label="Ver detalle: ${escHtml(c.titulo)}">
    <div class="conv-card-head">
      <div class="conv-card-badges">
        <span class="badge ${badgeClass(c.estado)}">${escHtml(c.estado)}</span>
        ${chip}
      </div>
      <div class="conv-card-actions">
        <button class="btn-icon-sm danger" onclick="event.stopPropagation(); deleteConvocatoria('${c.id}', '${escHtml(c.titulo).replace(/'/g, "\\'")}')" title="Eliminar">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </button>
      </div>
    </div>

    <div class="conv-card-title" title="${escHtml(c.titulo)}">${escHtml(c.titulo)}</div>

    <div class="conv-card-meta">
      <div class="meta-item" title="Institución">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
        <strong>${escHtml(c.fuente_nombre || '—')}</strong>
      </div>
      ${c.regiones && c.regiones.length ? `
      <div class="meta-item" title="Región">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
        <span>${escHtml(c.regiones.join(', '))}</span>
      </div>` : ''}
      ${c.monto != null ? `
      <div class="meta-item" title="Monto">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
        <strong style="color:var(--green)">${fmt(c.monto)}</strong>
      </div>` : ''}
    </div>

    <div class="conv-card-footer">
      ${urlBtn}
      <button class="card-detail-btn" onclick="event.stopPropagation(); viewDetail('${c.id}')" title="Ver detalle completo">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
        Detalle
      </button>
    </div>
  </div>`;
}

/* ── PAGINATION ──────────────────────────────────────────────── */
function renderConvPagination() {
  const el    = $('#convPagination');
  const pages = Math.ceil(state.convTotal / PAGE_SIZE);
  if (pages <= 1) { el.innerHTML = ''; return; }

  const current = Math.floor(state.convOffset / PAGE_SIZE);
  let html = `<button ${current === 0 ? 'disabled' : ''} onclick="goConvPage(${current - 1})">← Anterior</button>`;

  const start = Math.max(0, current - 2);
  const end   = Math.min(pages - 1, current + 2);
  for (let i = start; i <= end; i++) {
    html += `<button class="${i === current ? 'active' : ''}" onclick="goConvPage(${i})">${i + 1}</button>`;
  }
  html += `<button ${current >= pages - 1 ? 'disabled' : ''} onclick="goConvPage(${current + 1})">Siguiente →</button>`;
  el.innerHTML = html;
}

window.goConvPage = function(p) {
  state.convOffset = p * PAGE_SIZE;
  loadRadar();
  window.scrollTo({ top: 0, behavior: 'smooth' });
};

/* ── INSTITUCIÓN SELECTOR ────────────────────────────────────── */
async function initInstSelector() {
  try {
    const fuentes = await apiFetch('/fuentes');
    state.fuentes = fuentes;
    populateInstDropdown(fuentes);
    populateAdminFuentes(fuentes);
  } catch (e) {
    console.error('Error cargando fuentes:', e);
  }
}

function populateInstDropdown(fuentes) {
  const container = $('#instOptions');
  const allOption = buildInstOption(null, 'Todas las instituciones', fuentes.reduce((s, f) => s + (f.abiertas || 0), 0));
  container.innerHTML = allOption + fuentes.map(f => buildInstOption(f.id, f.nombre, f.abiertas)).join('');

  // Mark first as selected
  selectInstOption(null, 'Todas las instituciones');
}

function buildInstOption(id, nombre, abiertas) {
  const countClass = abiertas > 0 ? '' : 'zero';
  return `
  <div class="inst-option ${id === state.selectedFuenteId ? 'selected' : ''}"
       role="option"
       onclick="selectInstOption('${id}', '${escHtml(nombre).replace(/'/g, "\\'")}')"
       data-id="${id ?? ''}"
       tabindex="0">
    <div class="inst-option-name">${escHtml(nombre)}</div>
    <span class="inst-option-count ${countClass}">${abiertas ?? 0} activas</span>
  </div>`;
}

window.selectInstOption = function(id, nombre) {
  state.selectedFuenteId     = id || null;
  state.selectedFuenteNombre = id ? nombre : null;
  state.convOffset = 0;

  // Update button label
  $('#instSelectorLabel').textContent = nombre || 'Todas las instituciones';

  // Update selected class in dropdown
  $$('.inst-option').forEach(el => {
    el.classList.toggle('selected', el.dataset.id === (id ?? ''));
  });

  // Close dropdown
  closeInstDropdown();

  // If on radar page, reload
  if (state.page === 'radar') loadRadar();
};

function openInstDropdown() {
  $('#instDropdown').classList.add('open');
  $('#instSelectorBtn').classList.add('open');
  $('#instSearchInput').focus();
  $('#instSearchInput').value = '';
  filterInstOptions('');
}

function closeInstDropdown() {
  $('#instDropdown').classList.remove('open');
  $('#instSelectorBtn').classList.remove('open');
}

function filterInstOptions(query) {
  $$('.inst-option').forEach(el => {
    const name = el.querySelector('.inst-option-name').textContent.toLowerCase();
    el.style.display = name.includes(query.toLowerCase()) ? '' : 'none';
  });
}

/* ═══════════════════════════════════════════════════════════════
   INSTITUCIONES PAGE
═══════════════════════════════════════════════════════════════ */

async function loadInstituciones() {
  const grid = $('#instGrid');
  grid.innerHTML = '<div class="page-loader"><div class="spinner"></div><span>Cargando instituciones...</span></div>';

  try {
    const fuentes = await apiFetch('/fuentes');
    state.fuentes = fuentes;

    if (!fuentes.length) {
      grid.innerHTML = '<div class="empty-state"><p>Sin instituciones registradas.</p></div>';
      return;
    }

    grid.innerHTML = fuentes.map(f => buildInstCard(f)).join('');
  } catch (e) {
    toast('Error al cargar instituciones', 'error');
    grid.innerHTML = '<div class="empty-state"><p>Error al cargar.</p></div>';
  }
}

function buildInstCard(f) {
  const initials = institutionInitials(f.nombre);
  const lastSync = f.ultima_ejecucion ? fmtRelative(f.ultima_ejecucion) : 'Nunca';

  return `
  <div class="inst-card" title="Tarjeta de la institución ${escHtml(f.nombre)}. Click en 'Ver activas' para filtrar el radar por esta fuente.">
    <div class="inst-card-head">
      <div class="inst-logo">${escHtml(initials)}</div>
      <div>
        <div class="inst-card-name">${escHtml(f.nombre)}</div>
        <div class="inst-card-url">${escHtml(f.url_base)}</div>
      </div>
    </div>

    <div class="inst-stats">
      <div class="inst-stat" title="Convocatorias con estado ABIERTO en la última sincronización.">
        <div class="inst-stat-num" style="color:var(--green)">${f.abiertas ?? 0}</div>
        <div class="inst-stat-lbl">Activas</div>
      </div>
      <div class="inst-stat" title="Total de convocatorias registradas para esta institución, independientemente de su estado.">
        <div class="inst-stat-num">${f.total_convocatorias ?? 0}</div>
        <div class="inst-stat-lbl">Total</div>
      </div>
    </div>

    <div style="font-size:0.75rem;color:var(--text-3);display:flex;justify-content:space-between;align-items:center" title="Fecha del último scraping ejecutado contra esta fuente.">
      <span>Última sync: <strong>${escHtml(lastSync)}</strong></span>
      <span class="badge ${f.activa ? 'badge-green' : 'badge-gray'}" title="${f.activa ? 'Fuente incluida en los próximos ciclos de scraping.' : 'Fuente excluida de los próximos ciclos. Se puede reactivar desde la palanca.'}">${f.activa ? 'Activa' : 'Inactiva'}</span>
    </div>

    <div class="inst-card-footer">
      <button class="btn-sm primary" onclick="filterByInstitution('${f.id}', '${escHtml(f.nombre).replace(/'/g, "\\'")}')" title="Filtrar el radar por esta institución.">
        Ver activas
      </button>
      <a class="btn-sm" href="${escHtml(f.url_base)}" target="_blank" rel="noopener" onclick="event.stopPropagation()" title="Abrir el portal institucional en una pestaña nueva.">
        Ir al portal
      </a>
    </div>
  </div>`;
}

window.filterByInstitution = function(fuenteId, nombre) {
  state.selectedFuenteId     = fuenteId;
  state.selectedFuenteNombre = nombre;
  state.convOffset = 0;

  $('#instSelectorLabel').textContent = nombre;
  $$('.inst-option').forEach(el => {
    el.classList.toggle('selected', el.dataset.id === fuenteId);
  });

  $('#soloActivasToggle').checked = true;
  navigate('radar');
};

/* ═══════════════════════════════════════════════════════════════
   BRIEFING
═══════════════════════════════════════════════════════════════ */

async function loadBriefing() {
  const content = $('#briefingContent');
  const loader  = $('#briefingLoader');
  content.innerHTML = '';
  loader.style.display = 'flex';

  try {
    // Traer todas las activas (hasta 200)
    const data = await apiFetch('/convocatorias?estado=ABIERTO&orden=por_vencer&limit=200');

    if (!data.length) {
      loader.style.display = 'none';
      content.innerHTML = '<div class="empty-state"><p>No hay convocatorias activas en este momento.</p></div>';
      return;
    }

    // Agrupar por institución
    const byFuente = {};
    data.forEach(c => {
      const key = c.fuente_nombre || 'Sin institución';
      if (!byFuente[key]) byFuente[key] = [];
      byFuente[key].push(c);
    });

    // Fecha del briefing
    const fechaHoy = new Date().toLocaleDateString('es-CL', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

    let html = `
      <div style="margin-bottom:20px; padding:16px 20px; background:var(--bg-card); border:1px solid var(--border); border-radius:var(--r-lg); display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px;">
        <div>
          <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:.08em;color:var(--text-3);font-weight:600;margin-bottom:3px">Reporte generado</div>
          <div style="font-size:0.95rem;font-weight:600;color:var(--text-0)">${escHtml(fechaHoy)}</div>
        </div>
        <div style="display:flex;gap:12px;">
          <div style="text-align:center">
            <div style="font-size:1.6rem;font-weight:800;color:var(--green);letter-spacing:-0.04em">${data.length}</div>
            <div style="font-size:0.68rem;color:var(--text-3);text-transform:uppercase;letter-spacing:.05em">Activas</div>
          </div>
          <div style="width:1px;background:var(--border)"></div>
          <div style="text-align:center">
            <div style="font-size:1.6rem;font-weight:800;color:var(--blue);letter-spacing:-0.04em">${Object.keys(byFuente).length}</div>
            <div style="font-size:0.68rem;color:var(--text-3);text-transform:uppercase;letter-spacing:.05em">Instituciones</div>
          </div>
          <div style="width:1px;background:var(--border)"></div>
          <div style="text-align:center">
            <div style="font-size:1.6rem;font-weight:800;color:var(--amber);letter-spacing:-0.04em">${data.filter(c => { const d = diasHastaCierre(c.fecha_cierre); return d !== null && d <= 30 && d >= 0; }).length}</div>
            <div style="font-size:0.68rem;color:var(--text-3);text-transform:uppercase;letter-spacing:.05em">Cierran en 30d</div>
          </div>
        </div>
      </div>`;

    for (const [instNombre, convs] of Object.entries(byFuente)) {
      const initials = institutionInitials(instNombre);
      html += `
        <div class="briefing-section" style="margin-bottom:14px">
          <div class="briefing-section-header">
            <h3>
              <span style="width:32px;height:32px;border-radius:6px;background:var(--accent-dim);color:var(--accent-h);display:inline-flex;align-items:center;justify-content:center;font-size:0.75rem;font-weight:800">${escHtml(initials)}</span>
              ${escHtml(instNombre)}
            </h3>
            <span class="briefing-inst-badge">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              ${convs.length} activa${convs.length !== 1 ? 's' : ''}
            </span>
          </div>
          <table class="briefing-table">
            <thead>
              <tr>
                <th>Convocatoria</th>
                <th style="width:100px">Región</th>
                <th style="width:120px">Monto</th>
                <th style="width:100px">Cierre</th>
                <th style="width:90px">Urgencia</th>
                <th style="width:120px">URL directa</th>
              </tr>
            </thead>
            <tbody>
              ${convs.map(c => {
                const dias = diasHastaCierre(c.fecha_cierre);
                return `<tr>
                  <td class="briefing-title-cell">${escHtml(c.titulo)}</td>
                  <td><span style="font-size:0.78rem;color:var(--text-2)">${escHtml(c.regiones && c.regiones.length ? c.regiones.join(', ') : 'Nacional')}</span></td>
                  <td><span style="font-weight:600;color:var(--green)">${c.monto != null ? fmt(c.monto) : '—'}</span></td>
                  <td><span style="font-size:0.82rem;color:var(--text-1)">${fmtDate(c.fecha_cierre)}</span></td>
                  <td>${urgencyChip(dias)}</td>
                  <td>
                    ${c.url_detalle
                      ? `<a class="briefing-link" href="${escHtml(c.url_detalle)}" target="_blank" rel="noopener">
                          Abrir
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                        </a>`
                      : '<span style="color:var(--text-3);font-size:0.75rem">Sin URL</span>'}
                  </td>
                </tr>`;
              }).join('')}
            </tbody>
          </table>
        </div>`;
    }

    content.innerHTML = html;
  } catch (e) {
    toast('Error al generar briefing', 'error');
    content.innerHTML = '<div class="empty-state"><p>Error al cargar datos para el briefing.</p></div>';
  } finally {
    loader.style.display = 'none';
  }
}

/* ═══════════════════════════════════════════════════════════════
   CONVOCATORIA DETAIL MODAL
═══════════════════════════════════════════════════════════════ */

window.viewDetail = async function(id) {
  const modal = $('#detailModal');
  const body  = $('#detailModalBody');

  $('#detailInstBadge').textContent = 'Cargando...';
  body.innerHTML = '<div class="page-loader"><div class="spinner"></div><span>Cargando detalle...</span></div>';
  modal.classList.add('active');

  try {
    const data = await apiFetch(`/convocatorias/${id}`);
    const dias  = diasHastaCierre(data.fecha_cierre);

    $('#detailInstBadge').innerHTML = `
      <span class="badge ${badgeClass(data.estado)}">${escHtml(data.estado)}</span>
      <span style="margin-left:8px;font-size:0.85rem;color:var(--text-2);font-weight:600">${escHtml(data.fuente_nombre || '—')}</span>`;

    body.innerHTML = `
      <div class="detail-hero">
        <div class="detail-hero-meta">
          ${urgencyChip(dias)}
          ${data.regiones && data.regiones.length ? `<span style="font-size:0.78rem;color:var(--text-3)">📍 ${escHtml(data.regiones.join(', '))}</span>` : ''}
        </div>
        <h2 style="margin-top:8px">${escHtml(data.titulo)}</h2>
      </div>

      <div class="detail-grid">
        <div class="detail-field">
          <label>Monto</label>
          <span style="color:var(--green)">${data.monto != null ? fmt(data.monto) : '—'}</span>
        </div>
        <div class="detail-field">
          <label>Apertura</label>
          <span>${fmtDate(data.fecha_apertura)}</span>
        </div>
        <div class="detail-field">
          <label>Cierre</label>
          <span style="color:${dias !== null && dias <= 30 ? 'var(--amber)' : 'var(--text-0)'}">${fmtDate(data.fecha_cierre)}</span>
        </div>
        <div class="detail-field">
          <label>Días restantes</label>
          <span style="color:${dias !== null && dias <= 10 ? 'var(--red)' : dias !== null && dias <= 30 ? 'var(--amber)' : 'var(--text-0)'}">
            ${dias === null ? '—' : dias < 0 ? 'Vencida' : `${dias} días`}
          </span>
        </div>
        <div class="detail-field">
          <label>Actualizada</label>
          <span>${fmtDateTime(data.actualizado_en)}</span>
        </div>
      </div>

      ${data.url_detalle ? `
      <div class="detail-cta">
        <a href="${escHtml(data.url_detalle)}" target="_blank" rel="noopener noreferrer" class="btn-cta">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
          Ir a Postulación Oficial — ${escHtml(data.fuente_nombre || '')}
        </a>
        <div style="display:flex;align-items:center;gap:6px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--r);padding:8px 12px;overflow:hidden">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--text-3);flex-shrink:0"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
          <span style="font-size:0.75rem;font-family:var(--font-mono);color:var(--text-3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(data.url_detalle)}</span>
        </div>
      </div>` : `
      <div style="padding:12px;background:var(--bg-2);border:1px dashed var(--border);border-radius:var(--r);text-align:center;color:var(--text-3);font-size:0.85rem;margin-bottom:16px">
        Sin URL directa registrada para esta convocatoria
      </div>`}

      ${data.descripcion ? `
      <div class="detail-desc">
        <h3>Descripción</h3>
        <p>${escHtml(data.descripcion)}</p>
      </div>` : ''}

      <div class="detail-history">
        <h3 style="display:flex;align-items:center;justify-content:space-between">
          Historial de seguimiento
          <span class="badge badge-gray">${data.historial_cambios.length} registros</span>
        </h3>
        ${data.historial_cambios.length
          ? data.historial_cambios.map(ev => `
            <div class="timeline-item">
              <div class="timeline-date">${fmtDateTime(ev.fecha_deteccion)}</div>
              <span class="timeline-type">${ev.tipo} ${ev.es_relevante ? '★' : ''}</span>
              <ul class="delta-list">
                ${ev.deltas.map(d => `
                  <li>
                    <span class="delta-field">${escHtml(d.campo)}</span>
                    <span class="delta-old">${escHtml(d.valor_anterior ?? 'N/A')}</span>
                    →
                    <span class="delta-new">${escHtml(d.valor_nuevo ?? 'N/A')}</span>
                  </li>`).join('')}
              </ul>
            </div>`).join('')
          : '<p style="color:var(--text-3);font-size:0.85rem;padding:12px;background:var(--bg-2);border-radius:var(--r);text-align:center">Sin historial de cambios registrado</p>'}
      </div>`;

  } catch (e) {
    body.innerHTML = '<p style="color:var(--red);padding:20px">Error al cargar el detalle.</p>';
  }
};

/* ═══════════════════════════════════════════════════════════════
   DELETE
═══════════════════════════════════════════════════════════════ */

window.deleteConvocatoria = function(id, titulo) {
  showConfirm('Eliminar Convocatoria', `¿Eliminar "${titulo}"? Esta acción no se puede deshacer.`, async () => {
    try {
      await apiFetch(`/convocatorias/${id}`, { method: 'DELETE' });
      toast('Convocatoria eliminada', 'success');
      if (state.page === 'radar') loadRadar();
    } catch (e) {
      toast('Error al eliminar', 'error');
    }
  });
};

window.deleteFuente = function(id, nombre) {
  showConfirm('Eliminar Fuente', `¿Eliminar "${nombre}" y todas sus convocatorias? Esta acción no se puede deshacer.`, async () => {
    try {
      await apiFetch(`/fuentes/${id}`, { method: 'DELETE' });
      toast('Fuente eliminada', 'success');
      populateAdminFuentes(state.fuentes.filter(f => f.id !== id));
    } catch (e) {
      toast('Error al eliminar fuente', 'error');
    }
  });
};

/* ═══════════════════════════════════════════════════════════════
   ADMIN — FUENTES
═══════════════════════════════════════════════════════════════ */

function populateAdminFuentes(fuentes) {
  const body = $('#fuentesBody');
  if (!fuentes || !fuentes.length) {
    body.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-3);padding:2rem">Sin fuentes registradas</td></tr>';
    return;
  }

  body.innerHTML = fuentes.map(f => `
    <tr>
      <td>
        <button class="toggle-btn ${f.activa ? 'on' : ''}" onclick="toggleFuente('${f.id}', this)" title="${f.activa ? 'Desactivar esta fuente (no se incluirá en los próximos ciclos de scraping)' : 'Activar esta fuente (se incluirá en los próximos ciclos de scraping)'}" aria-label="Cambiar estado de la fuente"></button>
      </td>
      <td>
        <span class="fuente-name">${escHtml(f.nombre)}</span>
        <span class="fuente-url">${escHtml(f.url_base)}</span>
      </td>
      <td><span style="font-weight:700;color:var(--green)">${f.abiertas ?? 0}</span></td>
      <td><span style="font-weight:600;color:var(--text-0)">${f.total_convocatorias ?? 0}</span></td>
      <td><span style="font-size:0.78rem;color:var(--text-3)">${fmtRelative(f.ultima_ejecucion)}</span></td>
      <td>
        <button class="btn-icon-sm danger" onclick="deleteFuente('${f.id}', '${escHtml(f.nombre).replace(/'/g, "\\'")}')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </button>
      </td>
    </tr>`).join('');
}

window.toggleFuente = async function(id, btn) {
  try {
    const result = await apiFetch(`/fuentes/${id}/toggle`, { method: 'PATCH' });
    btn.classList.toggle('on', result.activa);
    toast(`${result.nombre}: ${result.activa ? 'activada' : 'desactivada'}`, 'success');
    // Update state
    const f = state.fuentes.find(f => f.id === id);
    if (f) f.activa = result.activa;
  } catch (e) {
    toast('Error al cambiar estado', 'error');
  }
};

/* ═══════════════════════════════════════════════════════════════
   ADMIN — NOTIFICACIONES
═══════════════════════════════════════════════════════════════ */

async function loadNotificaciones() {
  try {
    const [configs, history] = await Promise.all([
      apiFetch('/config/notificaciones'),
      apiFetch('/notificaciones?limite=30'),
    ]);
    renderNotifConfigs(configs);
    renderNotifHistory(history);
  } catch (e) {
    toast('Error al cargar notificaciones', 'error');
  }
}

function renderNotifConfigs(configs) {
  const el = $('#notifConfigList');
  if (!configs.length) { el.innerHTML = '<p class="muted-msg">Sin canales configurados</p>'; return; }

  el.innerHTML = configs.map(c => {
    const isTg = c.tipo === 'TELEGRAM';
    const detail = isTg
      ? `Chat: ${c.configuracion.chat_id || '—'} · Token: ****${(c.configuracion.token || '').slice(-4)}`
      : `${c.configuracion.host || '—'} → ${(c.configuracion.target_emails || []).join(', ')}`;
    return `
      <div class="config-item">
        <div class="config-icon ${isTg ? 'tg' : 'em'}">${isTg ? 'TG' : '@ '}</div>
        <div class="config-info">
          <h4>${escHtml(c.nombre)}</h4>
          <p>${escHtml(detail)}</p>
        </div>
        <div class="config-actions">
          <button class="toggle-btn ${c.activa ? 'on' : ''}" onclick="toggleNotifConfig('${c.id}', this)" title="${c.activa ? 'Desactivar este canal de notificación' : 'Activar este canal de notificación'}" aria-label="Cambiar estado del canal"></button>
          <button class="btn-icon-sm danger" onclick="deleteNotifConfig('${c.id}', '${escHtml(c.nombre).replace(/'/g, "\\'")}')">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </div>
      </div>`;
  }).join('');
}

function renderNotifHistory(history) {
  const el = $('#notifHistoryList');
  if (!history.length) { el.innerHTML = '<p class="muted-msg">Sin envíos registrados</p>'; return; }

  el.innerHTML = history.map(n => `
    <div class="notif-item">
      <span class="badge ${n.estado === 'ENVIADO' ? 'badge-green' : n.estado === 'FALLIDO' ? 'badge-red' : 'badge-gray'}" style="font-size:0.6rem">${escHtml(n.estado)}</span>
      <span class="notif-dest">${escHtml(n.destinatario)}</span>
      <span class="badge ${n.canal === 'TELEGRAM' ? 'badge-blue' : 'badge-amber'}" style="font-size:0.6rem">${escHtml(n.canal)}</span>
      <span class="notif-date">${fmtRelative(n.enviado_en)}</span>
    </div>`).join('');
}

window.toggleNotifConfig = async function(id, btn) {
  try {
    const r = await apiFetch(`/config/notificaciones/${id}/toggle`, { method: 'PATCH' });
    btn.classList.toggle('on', r.activa);
    toast(`${r.nombre}: ${r.activa ? 'activado' : 'desactivado'}`, 'success');
  } catch (e) {
    toast('Error al cambiar estado', 'error');
  }
};

window.deleteNotifConfig = function(id, nombre) {
  showConfirm('Eliminar Canal', `¿Eliminar el canal "${nombre}"?`, async () => {
    try {
      await apiFetch(`/config/notificaciones/${id}`, { method: 'DELETE' });
      toast('Canal eliminado', 'success');
      loadNotificaciones();
    } catch (e) {
      toast('Error al eliminar', 'error');
    }
  });
};

/* ═══════════════════════════════════════════════════════════════
   ADMIN — AUDIT LOG
═══════════════════════════════════════════════════════════════ */

async function loadAudit() {
  const body  = $('#auditBody');
  const loader = $('#auditLoader');
  loader.textContent = 'Cargando...';

  try {
    const nivel = $('#filterAuditNivel').value;
    const params = new URLSearchParams({ limite: '100' });
    if (nivel) params.set('nivel', nivel);
    const logs = await apiFetch(`/audit-logs?${params}`);
    renderAudit(logs);
  } catch (e) {
    toast('Error al cargar audit log', 'error');
  } finally {
    loader.textContent = '';
  }
}

function renderAudit(logs) {
  const body = $('#auditBody');
  if (!logs.length) {
    body.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-3);padding:2rem">Sin registros</td></tr>';
    return;
  }

  body.innerHTML = logs.map(l => {
    const badge = l.nivel === 'ERROR' ? 'badge-red' : l.nivel === 'WARNING' ? 'badge-amber' : 'badge-green';
    return `
      <tr>
        <td><span class="badge ${badge}">${escHtml(l.nivel)}</span></td>
        <td><span style="font-family:var(--font-mono);font-size:0.76rem;color:var(--text-3)">${escHtml(l.modulo)}</span></td>
        <td><span style="display:block;max-width:380px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(l.mensaje)}">${escHtml(l.mensaje)}</span></td>
        <td><span style="font-size:0.78rem;color:var(--text-3)">${escHtml(l.fuente_nombre || '—')}</span></td>
        <td><span style="font-size:0.76rem;font-family:var(--font-mono);color:var(--text-3)">${fmtDateTime(l.creado_en)}</span></td>
      </tr>`;
  }).join('');
}

/* ═══════════════════════════════════════════════════════════════
   SUSCRIPCIONES — CRUD unificado
═══════════════════════════════════════════════════════════════ */

/** Estado local de la suscripción activa. */
let subState = {
  id: null,
  chat_id: '',
  nombre: '',
  regiones: [],
  activa: true,
  confirmado: true,
  existe: false,     // true si ya tiene suscripción en BD
  dirty: false,      // true si hay cambios sin guardar
  guardando: false,
};

async function loadSuscripciones() {
  subState = {
    id: null, chat_id: '', nombre: '', regiones: [],
    activa: true, confirmado: true, existe: false, dirty: false, guardando: false,
  };
  // Cargar grid de regiones (una sola vez)
  if (!window._regionesCargadas) {
    try {
      const data = await apiFetch('/suscripciones/regiones');
      const grid = $('#subRegiones');
      grid.innerHTML = data.regiones.map(r =>
        `<label><input type="checkbox" value="${escHtml(r)}" onchange="onRegionToggle()"> ${escHtml(r)}</label>`
      ).join('');
      window._regionesCargadas = true;
    } catch (e) {
      console.error('Error cargando regiones:', e);
    }
  }
  // Resetear UI
  $('#subChatId').value = '';
  $('#subNombre').value = '';
  descheckearTodas();
  $('#suscContent').style.display = 'none';
  $('#suscEmpty').style.display = 'block';
  $('.susc-id-bar').classList.remove('susc-id-bar--loaded');
  actualizarCount();
  ocultarFeedback();
}

window.buscarSuscripcion = async function () {
  const chatId = $('#subChatId').value.trim();
  if (!chatId) { mostrarFeedback('Ingresá un Chat ID', 'error'); return; }

  mostrarFeedback('Buscando...', 'info');
  try {
    const data = await apiFetch(`/suscripciones/${encodeURIComponent(chatId)}`);
    // Suscripción existente
    subState.id = data.id;
    subState.chat_id = data.chat_id;
    subState.nombre = data.nombre || '';
    subState.regiones = data.regiones || [];
    subState.activa = data.activa;
    subState.confirmado = data.confirmado;
    subState.existe = true;
    subState.dirty = false;

    renderSubExistente(data);
    ocultarFeedback();
    $('.susc-id-bar').classList.add('susc-id-bar--loaded');
  } catch (e) {
    // No existe — modo creación
    subState.chat_id = chatId;
    subState.existe = false;
    subState.regiones = [];
    subState.activa = true;
    subState.dirty = false;

    renderSubNueva();
    ocultarFeedback();
    $('.susc-id-bar').classList.add('susc-id-bar--loaded');
  }
};

function renderSubExistente(data) {
  $('#suscContent').style.display = 'block';
  $('#suscEmpty').style.display = 'none';

  // Status bar
  $('#suscNombreDisplay').textContent = data.nombre || 'Sin nombre';
  $('#suscMeta').textContent = `Chat ID: ${data.chat_id}`;
  $('#subNombre').value = data.nombre || '';

  // Badges
  if (data.activa) {
    $('#suscBadgeActiva').style.display = 'inline-flex';
    $('#suscBadgePausada').style.display = 'none';
  } else {
    $('#suscBadgeActiva').style.display = 'none';
    $('#suscBadgePausada').style.display = 'inline-flex';
  }
  $('#suscBadgeCreada').style.display = 'none';
  $('#suscAvatar').textContent = data.nombre ? getInitial(data.nombre) : '👤';

  // Checkear regiones
  checkearRegiones(subState.regiones);
  actualizarCount();

  // Acciones
  $('#subGuardarBtn').disabled = true;
  $('#subGuardarLabel').textContent = 'Guardar cambios';
  $('#subPausarBtn').style.display = 'inline-flex';
  $('#subPausarLabel').textContent = data.activa ? 'Pausar' : 'Reanudar';
  $('#subEliminarBtn').style.display = 'inline-flex';
}

function renderSubNueva() {
  $('#suscContent').style.display = 'block';
  $('#suscEmpty').style.display = 'none';

  // Status bar — nueva
  $('#suscNombreDisplay').textContent = 'Nueva suscripción';
  $('#suscMeta').textContent = `Chat ID: ${subState.chat_id}`;
  $('#subNombre').value = '';
  $('#suscBadgeActiva').style.display = 'none';
  $('#suscBadgePausada').style.display = 'none';
  $('#suscBadgeCreada').style.display = 'inline-flex';
  $('#suscAvatar').textContent = '🆕';

  // Sin regiones checkeadas
  descheckearTodas();
  actualizarCount();

  // Acciones
  $('#subGuardarBtn').disabled = false;
  $('#subGuardarLabel').textContent = 'Crear suscripción';
  $('#subPausarBtn').style.display = 'none';
  $('#subEliminarBtn').style.display = 'none';
}

/** Se ejecuta cada vez que se clickea un checkbox de región. */
window.onRegionToggle = function () {
  const seleccionadas = obtenerRegionesSeleccionadas();
  actualizarCount();
  // Marcar dirty si cambió respecto al estado guardado
  const sorted1 = [...seleccionadas].sort();
  const sorted2 = [...subState.regiones].sort();
  const iguales = sorted1.length === sorted2.length && sorted1.every((v, i) => v === sorted2[i]);
  subState.dirty = !iguales || ($('#subNombre').value.trim() || '') !== (subState.nombre || '');
  $('#subGuardarBtn').disabled = !subState.dirty;
  if (subState.dirty) {
    $('#subGuardarLabel').textContent = subState.existe ? 'Guardar cambios' : 'Crear suscripción';
  } else {
    $('#subGuardarLabel').textContent = subState.existe ? 'Guardar cambios' : 'Crear suscripción';
  }
};

window.guardarSuscripcion = async function () {
  if (subState.guardando) return;
  subState.guardando = true;

  const nombre = $('#subNombre').value.trim() || null;
  const regiones = obtenerRegionesSeleccionadas();

  if (!regiones.length) {
    mostrarFeedback('Seleccioná al menos una región', 'error');
    subState.guardando = false;
    return;
  }

  const btn = $('#subGuardarBtn');
  btn.disabled = true;
  const label = $('#subGuardarLabel');
  const originalText = label.textContent;
  label.textContent = 'Guardando...';

  try {
    if (subState.existe) {
      // PATCH
      const data = await apiFetch(`/suscripciones/${subState.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ regiones, activa: subState.activa, nombre }),
      });
      mostrarFeedback('Suscripción actualizada', 'success');
      subState.nombre = nombre || '';
      subState.regiones = data.regiones || [];
    } else {
      // POST
      const data = await apiFetch('/suscripciones', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: subState.chat_id, nombre, regiones }),
      });
      mostrarFeedback('Suscripción creada exitosamente', 'success');
      subState.id = data.id;
      subState.nombre = nombre || '';
      subState.regiones = data.regiones || [];
      subState.activa = data.activa;
      subState.existe = true;
      // Re-render como existente
      renderSubExistente(data);
    }
    subState.dirty = false;
    $('#subGuardarBtn').disabled = true;
    $('#subGuardarLabel').textContent = 'Guardar cambios';
  } catch (e) {
    mostrarFeedback('Error al guardar suscripción', 'error');
  } finally {
    subState.guardando = false;
    label.textContent = originalText;
  }
};

window.toggleActiva = async function () {
  if (!subState.existe || !subState.id) return;
  const nuevaActiva = !subState.activa;
  try {
    await apiFetch(`/suscripciones/${subState.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ activa: nuevaActiva }),
    });
    subState.activa = nuevaActiva;
    if (nuevaActiva) {
      $('#suscBadgeActiva').style.display = 'inline-flex';
      $('#suscBadgePausada').style.display = 'none';
      $('#subPausarLabel').textContent = 'Pausar';
      mostrarFeedback('Suscripción reactivada', 'success');
    } else {
      $('#suscBadgeActiva').style.display = 'none';
      $('#suscBadgePausada').style.display = 'inline-flex';
      $('#subPausarLabel').textContent = 'Reanudar';
      mostrarFeedback('Suscripción pausada', 'success');
    }
  } catch (e) {
    mostrarFeedback('Error al cambiar estado', 'error');
  }
};

window.eliminarSuscripcion = function () {
  if (!subState.existe || !subState.id) return;
  showConfirm('Eliminar suscripción',
    '¿Eliminar esta suscripción? Vas a dejar de recibir alertas de Telegram.',
    async () => {
      try {
        await apiFetch(`/suscripciones/${subState.id}`, { method: 'DELETE' });
        toast('Suscripción eliminada', 'success');
        // Resetear todo
        await loadSuscripciones();
      } catch (e) {
        mostrarFeedback('Error al eliminar suscripción', 'error');
      }
    }
  );
};

// ─── HELPERS ────────────────────────────────────────────────────────────

function obtenerRegionesSeleccionadas() {
  return Array.from($$('#subRegiones input[type="checkbox"]:checked')).map(cb => cb.value);
}

function checkearRegiones(regiones) {
  const set = new Set(regiones);
  $$('#subRegiones input[type="checkbox"]').forEach(cb => {
    cb.checked = set.has(cb.value);
  });
}

function descheckearTodas() {
  $$('#subRegiones input[type="checkbox"]').forEach(cb => { cb.checked = false; });
}

function actualizarCount() {
  const n = $$('#subRegiones input[type="checkbox"]:checked').length;
  $('#subSelectedCount').textContent = n === 0 ? 'Ninguna seleccionada' : `${n} seleccionada${n !== 1 ? 's' : ''}`;
}

function mostrarFeedback(msg, tipo) {
  const el = $('#subFeedback');
  el.textContent = msg;
  el.className = `susc-feedback susc-feedback--${tipo}`;
  el.style.display = 'block';
}

function ocultarFeedback() {
  $('#subFeedback').style.display = 'none';
}

function getInitial(name) {
  return name ? name.trim().charAt(0).toUpperCase() : '👤';
}

/* ═══════════════════════════════════════════════════════════════
   ADMIN LOADER
═══════════════════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════════════════════════
   ADMIN LOADER
═══════════════════════════════════════════════════════════════ */

function loadAdmin() {
  // Cargar el tab activo
  const activeTab = $('.admin-tab.active');
  if (activeTab) loadAdminTab(activeTab.dataset.tab);
}

function loadAdminTab(tab) {
  switch (tab) {
    case 'fuentes':        populateAdminFuentes(state.fuentes); break;
    case 'notificaciones': loadNotificaciones(); break;
    case 'audit':          loadAudit(); break;
    case 'system-logs':    loadSystemLogs(); break;
  }
}

/* ═══════════════════════════════════════════════════════════════
   SYSTEM LOGS
═══════════════════════════════════════════════════════════════ */

async function loadSystemLogs() {
  const content = $('#systemLogsContent');
  const emptyMsg = $('#systemLogsEmpty');
  const btn = $('#btnRefreshLogs');
  
  if(btn) btn.classList.add('spinning');
  
  try {
    const res = await apiFetch('/debug/errors');
    if (res.error) {
      content.style.display = 'none';
      emptyMsg.style.display = 'block';
      emptyMsg.textContent = res.error;
    } else if (!res.content || res.content.trim() === '') {
      content.style.display = 'none';
      emptyMsg.style.display = 'block';
      emptyMsg.textContent = 'Sin errores registrados. Todo en orden.';
    } else {
      emptyMsg.style.display = 'none';
      content.style.display = 'block';
      content.textContent = res.content;
      content.scrollTop = content.scrollHeight; // Scroll to bottom
    }
  } catch (e) {
    toast('Error al cargar logs del sistema', 'error');
  } finally {
    if(btn) btn.classList.remove('spinning');
  }
}

async function clearSystemLogs() {
  showConfirm('Limpiar Logs', '¿Estás seguro de que deseas vaciar el archivo de logs del sistema?', async () => {
    try {
      await apiFetch('/debug/errors', { method: 'DELETE' });
      toast('Logs limpiados correctamente', 'success');
      loadSystemLogs();
    } catch (e) {
      toast('Error al limpiar logs', 'error');
    }
  });
}

async function copySystemLogs() {
  const text = $('#systemLogsContent').textContent;
  if (!text) {
    toast('No hay logs para copiar', 'warning');
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    toast('Logs copiados al portapapeles', 'success');
  } catch (err) {
    toast('Error al copiar al portapapeles', 'error');
  }
}

/* ═══════════════════════════════════════════════════════════════
   NOTIFICATION FORMS
═══════════════════════════════════════════════════════════════ */

function setupForms() {
  const tgForm = $('#telegramForm');
  const emForm = $('#emailForm');
  const tabs   = $$('#notifTypeTabs .tab');

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      $$('.notif-form').forEach(f => f.classList.remove('active'));
      $(tab.dataset.type === 'TELEGRAM' ? '#telegramForm' : '#emailForm').classList.add('active');
    });
  });

  tgForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await apiFetch('/config/notificaciones', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nombre: $('#tgNombre').value,
          tipo: 'TELEGRAM',
          configuracion: { token: $('#tgToken').value, chat_id: $('#tgChatId').value },
          activa: true,
        }),
      });
      tgForm.reset();
      toast('Canal Telegram agregado', 'success');
      loadNotificaciones();
    } catch (e) {
      toast('Error al guardar canal', 'error');
    }
  });

  emForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const targets = $('#emTargets').value.split(',').map(t => t.trim()).filter(Boolean);
    try {
      await apiFetch('/config/notificaciones', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nombre: $('#emNombre').value,
          tipo: 'EMAIL',
          configuracion: {
            host: $('#emHost').value,
            port: parseInt($('#emPort').value),
            user: $('#emUser').value,
            password: $('#emPass').value,
            from_email: $('#emFrom').value,
            target_emails: targets,
            use_tls: true,
          },
          activa: true,
        }),
      });
      emForm.reset();
      $('#emPort').value = '587';
      toast('Canal Email agregado', 'success');
      loadNotificaciones();
    } catch (e) {
      toast('Error al guardar canal', 'error');
    }
  });
}

/* ═══════════════════════════════════════════════════════════════
   INIT
═══════════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', async () => {

  setupForms();

  // ── NAV ──
  $$('.nav-item[data-page]').forEach(btn => {
    btn.addEventListener('click', () => navigate(btn.dataset.page));
  });

  // ── SIDEBAR TOGGLE ──
  $('#sidebarToggle').addEventListener('click', () => {
    const sb = $('#sidebar');
    sb.classList.toggle('collapsed');
    document.body.classList.toggle('sidebar-collapsed');
  });

  // ── MOBILE MENU ──
  $('#mobileMenuBtn').addEventListener('click', () => {
    $('#sidebar').classList.toggle('mobile-open');
  });

  document.addEventListener('click', (e) => {
    if (!$('#sidebar').contains(e.target) && !$('#mobileMenuBtn').contains(e.target)) {
      $('#sidebar').classList.remove('mobile-open');
    }
  });

  // ── INST SELECTOR ──
  $('#instSelectorBtn').addEventListener('click', (e) => {
    e.stopPropagation();
    const isOpen = $('#instDropdown').classList.contains('open');
    if (isOpen) closeInstDropdown();
    else openInstDropdown();
  });

  $('#instSearchInput').addEventListener('input', () => {
    filterInstOptions($('#instSearchInput').value);
  });

  // Cerrar dropdown al hacer click afuera
  document.addEventListener('click', (e) => {
    if (!$('#instSelectorWrap').contains(e.target)) {
      closeInstDropdown();
    }
  });

  // ── REFRESH ──
  $('#refreshBtn').addEventListener('click', () => {
    const btn = $('#refreshBtn');
    btn.classList.add('spinning');
    loadPage(state.page);
    setTimeout(() => btn.classList.remove('spinning'), 1200);
  });

  // ── DEBUG WIPE ──
  const wipeBtn = $('#debugWipeBtn');
  if (wipeBtn) {
    wipeBtn.addEventListener('click', async () => {
      if (confirm("¡CUIDADO! Esto borrará TODA la base de datos (Convocatorias, Historial, Snapshots). ¿Continuar?")) {
        try {
          const res = await apiFetch('/debug/wipe', { method: 'DELETE' });
          if (res) {
            alert("Base de datos borrada con éxito.");
            window.location.reload();
          }
        } catch (e) {
          alert("Error al borrar BD: " + e.message);
        }
      }
    });
  }

  // ── SCRAPE MANUAL ──
  let scrapeEnCurso = false;
  let scrapePollInterval = null;

  async function checkScrapeStatus() {
    try {
      const r = await fetch('/api/v1/scrape/status');
      if (r.ok) {
        const data = await r.json();
        const btn = $('#scrapeBtn');
        if (data.en_curso) {
          if (!scrapeEnCurso) {
            scrapeEnCurso = true;
            btn.classList.add('spinning');
            if (!scrapePollInterval) {
              scrapePollInterval = setInterval(checkScrapeStatus, 3000);
            }
          }
        } else {
          if (scrapeEnCurso) {
            scrapeEnCurso = false;
            btn.classList.remove('spinning');
            if (scrapePollInterval) {
              clearInterval(scrapePollInterval);
              scrapePollInterval = null;
              toast('Scrape finalizado. Actualizando datos...', 'success');
              loadPage(state.page);
            }
          }
        }
      }
    } catch (e) {
      console.error("Error consultando estado de scrape:", e);
    }
  }

  // Verificar estado inicial al cargar
  checkScrapeStatus();

  $('#scrapeBtn').addEventListener('click', async () => {
    if (scrapeEnCurso) {
      toast('El scrape ya se encuentra en ejecución', 'info');
      return;
    }
    scrapeEnCurso = true;
    const btn = $('#scrapeBtn');
    btn.classList.add('spinning');
    toast('Scrape iniciado en segundo plano...', 'info');
    
    try {
      const r = await fetch('/api/v1/scrape', { method: 'POST' });
      if (!r.ok) {
        const errData = await r.json().catch(() => ({}));
        if (r.status === 409) {
          toast('Ya hay un scrape en ejecución', 'warning');
        } else {
          throw new Error(errData.detail || r.statusText);
        }
      }
      if (!scrapePollInterval) {
        scrapePollInterval = setInterval(checkScrapeStatus, 3000);
      }
    } catch (e) {
      if (!e.message.includes('Ya hay')) {
        toast(`Error: ${e.message}`, 'error');
        scrapeEnCurso = false;
        btn.classList.remove('spinning');
      }
    }
  });

  // ── FILTROS RADAR ──
  $('#soloActivasToggle').addEventListener('change', () => { state.convOffset = 0; loadRadar(); });
  const inclPermToggle = $('#incluirPermanentesToggle');
  if (inclPermToggle) {
    inclPermToggle.addEventListener('change', () => { state.convOffset = 0; loadRadar(); });
  }
  $('#filterOrden').addEventListener('change',       () => { state.convOffset = 0; loadRadar(); });
  $('#filterRegion').addEventListener('change',      () => { state.convOffset = 0; loadRadar(); });
  $('#searchInput').addEventListener('input', () => {
    clearTimeout(state.searchTimeout);
    state.searchTimeout = setTimeout(() => { state.convOffset = 0; loadRadar(); }, 350);
  });

  // ── ADMIN TABS ──
  $$('.admin-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      $$('.admin-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      $$('.admin-pane').forEach(p => p.classList.remove('active'));
      $(`#adminpane-${tab.dataset.tab}`).classList.add('active');
      loadAdminTab(tab.dataset.tab);
    });
  });

  // ── AUDIT FILTER ──
  $('#filterAuditNivel').addEventListener('change', loadAudit);

  // ── MODALS ──
  $('#detailModalClose').addEventListener('click', () => $('#detailModal').classList.remove('active'));
  $('#detailModal').addEventListener('click', (e) => {
    if (e.target === $('#detailModal')) $('#detailModal').classList.remove('active');
  });

  $('#confirmModalClose').addEventListener('click', () => { $('#confirmModal').classList.remove('active'); state.confirmCb = null; });
  $('#confirmModalCancel').addEventListener('click', () => { $('#confirmModal').classList.remove('active'); state.confirmCb = null; });
  $('#confirmModalOk').addEventListener('click', () => {
    $('#confirmModal').classList.remove('active');
    if (state.confirmCb) { state.confirmCb(); state.confirmCb = null; }
  });
  $('#confirmModal').addEventListener('click', (e) => {
    if (e.target === $('#confirmModal')) { $('#confirmModal').classList.remove('active'); state.confirmCb = null; }
  });

  // ── BRIEFING PRINT ──
  $('#printBriefingBtn').addEventListener('click', () => window.print());

  // ── KEYBOARD ──
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      $('#detailModal').classList.remove('active');
      $('#confirmModal').classList.remove('active');
      $('#sidebar').classList.remove('mobile-open');
      closeInstDropdown();
      state.confirmCb = null;
    }
  });

  // ── SUSCRIPCIONES: Enter en Chat ID busca automáticamente ──
  $('#subChatId').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      buscarSuscripcion();
    }
  });
  // Enter en nombre también guarda
  $('#subNombre').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && subState.existe && !$('#subGuardarBtn').disabled) {
      e.preventDefault();
      guardarSuscripcion();
    }
  });

  // ── BOOT ──
  // 1. Cargar fuentes e inicializar selector
  await initInstSelector();

  // 2. Navegar a radar (carga automática)
  navigate('radar');
});

/* ─── MODAL LOGS ──────────────────────────────────────────────── */

function abrirLogs() {
  const modal = $('#logsModal');
  if (modal) {
    modal.classList.add('active');
    cargarLogs();
  }
}

function cerrarLogs() {
  const modal = $('#logsModal');
  if (modal) modal.classList.remove('active');
}

async function cargarLogs() {
  const content = $('#logsContent');
  if (!content) return;
  content.textContent = "Cargando logs...";
  try {
    const res = await fetch(`${API}/debug/errors`);
    if (!res.ok) throw new Error("No se pudieron obtener los logs");
    const data = await res.json();
    if (data.error) {
      content.textContent = data.error;
    } else {
      content.textContent = data.content || "No hay logs registrados.";
    }
    content.scrollTop = content.scrollHeight;
  } catch (err) {
    content.textContent = "Error de red al cargar logs: " + err.message;
  }
}

async function copiarLogs() {
  const content = $('#logsContent');
  if (!content) return;
  try {
    await navigator.clipboard.writeText(content.textContent);
    showToast("Logs copiados al portapapeles", "success");
  } catch (err) {
    showToast("No se pudo copiar: " + err.message, "error");
  }
}

async function limpiarLogs() {
  try {
    const res = await fetch(`${API}/debug/errors`, { method: "DELETE" });
    if (!res.ok) throw new Error("No se pudo limpiar");
    showToast("Logs limpiados exitosamente", "success");
    cargarLogs();
  } catch (err) {
    showToast("Error al limpiar logs: " + err.message, "error");
  }
}

if ($('#logsModalClose')) $('#logsModalClose').addEventListener('click', cerrarLogs);
if ($('#btnCopiarLogs')) $('#btnCopiarLogs').addEventListener('click', copiarLogs);
if ($('#btnLimpiarLogs')) $('#btnLimpiarLogs').addEventListener('click', limpiarLogs);
