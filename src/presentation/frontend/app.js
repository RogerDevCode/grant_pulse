/**
 * GrantPulse — Frontend SPA
 * Vanilla JS, no framework. Server-side filtering, pagination, full CRUD.
 */

const API = '/api/v1';
const PAGE_SIZE = 50;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const state = {
  page: 'dashboard',
  convocatorias: [],
  fuentes: [],
  notifConfigs: [],
  notifHistory: [],
  auditLogs: [],
  stats: null,
  convOffset: 0,
  convTotal: 0,
  searchTimeout: null,
};

const PAGE_TITLES = {
  dashboard: 'Dashboard',
  convocatorias: 'Convocatorias',
  fuentes: 'Fuentes',
  notificaciones: 'Notificaciones',
  audit: 'Audit Log',
};

function fmt(n) {
  if (n == null) return '—';
  return new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP', maximumFractionDigits: 0 }).format(n);
}

function fmtDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('es-CL', { day: '2-digit', month: 'short', year: 'numeric' });
}

function fmtDateTime(d) {
  if (!d) return '—';
  return new Date(d).toLocaleString('es-CL', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function fmtRelative(d) {
  if (!d) return 'Nunca';
  const diff = Date.now() - new Date(d).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Ahora';
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  const days = Math.floor(hrs / 24);
  return `${days}d`;
}

function badgeClass(estado) {
  const e = (estado || '').toUpperCase();
  if (e.includes('ABIERT')) return 'badge-green';
  if (e.includes('CERRAD') || e.includes('FINALIZAD')) return 'badge-red';
  if (e.includes('PROXIMA')) return 'badge-amber';
  if (e === 'PUBLISH' || e === 'DESCONOCIDO') return 'badge-gray';
  return 'badge-blue';
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

function translateField(f) {
  const m = { estado: 'Estado', fecha_cierre: 'Fecha de Cierre', monto: 'Monto', titulo: 'Título', descripcion: 'Descripción', url_detalle: 'Enlace' };
  return m[f] || f;
}

function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  $('#toastContainer').appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

/* ── NAVIGATION ─────────────────────── */

function navigate(page) {
  state.page = page;
  $$('.page').forEach(p => p.classList.remove('active'));
  $(`#page-${page}`).classList.add('active');
  $$('.nav-item[data-page]').forEach(b => b.classList.toggle('active', b.dataset.page === page));
  $('#pageTitle').textContent = PAGE_TITLES[page] || page;
  loadPage(page);
}

function loadPage(page) {
  switch (page) {
    case 'dashboard': loadDashboard(); break;
    case 'convocatorias': loadConvocatorias(); break;
    case 'fuentes': loadFuentes(); break;
    case 'notificaciones': loadNotificaciones(); break;
    case 'audit': loadAudit(); break;
  }
}

/* ── API HELPERS ─────────────────────── */

async function apiFetch(path, opts = {}) {
  const r = await fetch(`${API}${path}`, opts);
  if (!r.ok) {
    const detail = r.status !== 204 ? await r.text().catch(() => '') : '';
    throw new Error(`${r.status}: ${detail}`);
  }
  if (r.status === 204) return null;
  return r.json();
}

/* ── DASHBOARD ───────────────────────── */

async function loadDashboard() {
  try {
    const stats = await apiFetch('/dashboard');
    state.stats = stats;
    renderStats(stats);
    renderDashFuentes();
    renderDashAperturas();
  } catch (e) {
    console.error('Dashboard error:', e);
  }
}

function renderStats(s) {
  $('#statsGrid').innerHTML = [
    { label: 'Fuentes Activas', value: s.fuentes_activas, cls: 'blue', total: s.total_fuentes },
    { label: 'Convocatorias', value: s.total_convocatorias, cls: '' },
    { label: 'Abiertas', value: s.convocatorias_abiertas, cls: 'green' },
    { label: 'Cerradas', value: s.convocatorias_cerradas, cls: 'red' },
    { label: 'Eventos', value: s.total_eventos, cls: '' },
    { label: 'Relevantes', value: s.eventos_relevantes, cls: 'amber' },
  ].map(c => `
    <div class="stat-card">
      <div class="stat-label">${c.label}${c.total != null ? ` / ${c.total}` : ''}</div>
      <div class="stat-value ${c.cls}">${c.value}</div>
    </div>
  `).join('');
}

async function renderDashFuentes() {
  try {
    const fuentes = await apiFetch('/fuentes');
    const el = $('#dashFuentes');
    if (!fuentes.length) { el.innerHTML = '<p style="color:var(--text-3);font-size:0.85rem">Sin fuentes registradas</p>'; return; }
    el.innerHTML = '<ul class="mini-list">' + fuentes.map(f => `
      <li>
        <span class="badge ${f.activa ? 'badge-green' : 'badge-gray'}" style="font-size:0.6rem">${f.activa ? 'ON' : 'OFF'}</span>
        <span style="font-weight:500;color:var(--text-0)">${escHtml(f.nombre)}</span>
        <span style="margin-left:auto;font-family:var(--font-mono);font-size:0.75rem;color:var(--text-3)">${f.abiertas} abiertas</span>
      </li>
    `).join('') + '</ul>';
  } catch (e) { /* ignore */ }
}

async function renderDashAperturas() {
  try {
    const conv = await apiFetch('/convocatorias?estado=ABIERTO&limit=5');
    const el = $('#dashAperturas');
    if (!conv.length) { el.innerHTML = '<p style="color:var(--text-3);font-size:0.85rem">Sin convocatorias abiertas</p>'; return; }
    el.innerHTML = '<ul class="mini-list">' + conv.map(c => `
      <li>
        <span class="badge badge-green" style="font-size:0.6rem">ABIERTA</span>
        <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-0);font-size:0.85rem;cursor:pointer" onclick="viewDetail('${c.id}')">${escHtml(c.titulo)}</span>
      </li>
    `).join('') + '</ul>';
  } catch (e) { /* ignore */ }
}

/* ── CONVOCATORIAS ───────────────────── */

async function loadConvocatorias() {
  const estado = $('#filterEstado').value;
  const fuenteId = $('#filterFuente').value;
  const search = $('#searchInput').value.trim();

  $('#convocatoriasLoader').style.display = '';
  $('#convocatoriasEmpty').style.display = 'none';

  try {
    const params = new URLSearchParams();
    params.set('limit', PAGE_SIZE);
    params.set('offset', state.convOffset);
    if (estado) params.set('estado', estado);
    if (fuenteId) params.set('fuente_id', fuenteId);
    if (search) params.set('search', search);

    const data = await apiFetch(`/convocatorias?${params}`);
    state.convocatorias = data;
    renderConvocatorias(data);

    const countParams = new URLSearchParams();
    if (estado) countParams.set('estado', estado);
    if (fuenteId) countParams.set('fuente_id', fuenteId);
    const count = await apiFetch(`/convocatorias/count?${countParams}`);
    state.convTotal = count.total;
    $('#resultCount').textContent = `${count.total} resultados`;
    renderConvPagination();
  } catch (e) {
    console.error('Convocatorias error:', e);
    toast('Error al cargar convocatorias', 'error');
  } finally {
    $('#convocatoriasLoader').style.display = 'none';
  }
}

function renderConvocatorias(items) {
  const body = $('#convocatoriasBody');
  if (!items.length) {
    body.innerHTML = '';
    $('#convocatoriasEmpty').style.display = '';
    return;
  }
  body.innerHTML = items.map(c => `
    <tr>
      <td><span class="badge ${badgeClass(c.estado)}">${escHtml(c.estado)}</span></td>
      <td><span class="cell-title" title="${escHtml(c.titulo)}">${escHtml(c.titulo)}</span></td>
      <td><span class="cell-fuente">${escHtml(c.fuente_nombre || '—')}</span></td>
      <td><span class="cell-monto">${c.monto != null ? fmt(c.monto) : '—'}</span></td>
      <td><span class="cell-date">${fmtDate(c.fecha_cierre)}</span></td>
      <td>
        <button class="btn-icon-sm" onclick="viewDetail('${c.id}')" title="Ver detalle">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
        </button>
        ${c.url_detalle ? `<a class="btn-icon-sm" href="${c.url_detalle}" target="_blank" rel="noopener" title="Ver en portal">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
        </a>` : ''}
      </td>
    </tr>
  `).join('');
}

function renderConvPagination() {
  const el = $('#convPagination');
  const pages = Math.ceil(state.convTotal / PAGE_SIZE);
  if (pages <= 1) { el.innerHTML = ''; return; }

  const current = Math.floor(state.convOffset / PAGE_SIZE);
  let html = `<button ${current === 0 ? 'disabled' : ''} onclick="goConvPage(${current - 1})">Anterior</button>`;

  const start = Math.max(0, current - 2);
  const end = Math.min(pages - 1, current + 2);
  for (let i = start; i <= end; i++) {
    html += `<button class="${i === current ? 'active' : ''}" onclick="goConvPage(${i})">${i + 1}</button>`;
  }

  html += `<button ${current >= pages - 1 ? 'disabled' : ''} onclick="goConvPage(${current + 1})">Siguiente</button>`;
  el.innerHTML = html;
}

window.goConvPage = function(p) {
  state.convOffset = p * PAGE_SIZE;
  loadConvocatorias();
};

/* ── CONVOCATORIA DETAIL ─────────────── */

window.viewDetail = async function(id) {
  const modal = $('#detailModal');
  const body = $('#detailModalBody');
  $('#detailModalTitle').textContent = 'Cargando...';
  body.innerHTML = '<div class="loader">Cargando detalle...</div>';
  modal.classList.add('active');

  try {
    const data = await apiFetch(`/convocatorias/${id}`);
    $('#detailModalTitle').textContent = data.titulo;

    body.innerHTML = `
      <div class="detail-grid">
        <div class="detail-field"><label>Estado</label><span class="badge ${badgeClass(data.estado)}">${escHtml(data.estado)}</span></div>
        <div class="detail-field"><label>Fuente</label><span>${escHtml(data.fuente_nombre || '—')}</span></div>
        <div class="detail-field"><label>Monto</label><span>${data.monto != null ? fmt(data.monto) : '—'}</span></div>
        <div class="detail-field"><label>Fecha Cierre</label><span>${fmtDate(data.fecha_cierre)}</span></div>
        <div class="detail-field"><label>Fecha Apertura</label><span>${fmtDate(data.fecha_apertura)}</span></div>
        <div class="detail-field"><label>Actualizado</label><span>${fmtDateTime(data.actualizado_en)}</span></div>
      </div>
      ${data.descripcion ? `<div class="detail-section"><h3>Descripción</h3><p style="font-size:0.88rem;color:var(--text-1);line-height:1.6">${escHtml(data.descripcion)}</p></div>` : ''}
      ${data.url_detalle ? `<div class="detail-section"><a href="${data.url_detalle}" target="_blank" rel="noopener" class="btn btn-primary" style="display:inline-flex">Ver en Portal &rarr;</a></div>` : ''}
      <div class="detail-section">
        <h3>Historial de Cambios (${data.historial_cambios.length})</h3>
        ${data.historial_cambios.length ? renderHistory(data.historial_cambios) : '<p style="color:var(--text-3);font-size:0.85rem">Sin cambios registrados</p>'}
      </div>
    `;
  } catch (e) {
    body.innerHTML = '<p style="color:var(--red)">Error al cargar detalle</p>';
  }
};

function renderHistory(events) {
  return events.map(ev => `
    <div class="timeline-item">
      <div class="timeline-date">${fmtDateTime(ev.fecha_deteccion)}</div>
      <span class="timeline-type ${ev.tipo === 'APERTURA' ? 'apertura' : 'modificacion'}">${ev.tipo} ${ev.es_relevante ? '★' : ''}</span>
      <ul class="delta-list">
        ${ev.deltas.map(d => `
          <li>
            <span class="delta-field">${translateField(d.campo)}</span>
            <span class="delta-old">${escHtml(d.valor_anterior || 'N/A')}</span>
            &rarr;
            <span class="delta-new">${escHtml(d.valor_nuevo || 'N/A')}</span>
          </li>
        `).join('')}
      </ul>
    </div>
  `).join('');
}

/* ── FUENTES ─────────────────────────── */

async function loadFuentes() {
  $('#fuentesLoader').style.display = '';
  try {
    const fuentes = await apiFetch('/fuentes');
    state.fuentes = fuentes;
    renderFuentes(fuentes);
    populateFuenteFilter(fuentes);
  } catch (e) {
    toast('Error al cargar fuentes', 'error');
  } finally {
    $('#fuentesLoader').style.display = 'none';
  }
}

function renderFuentes(fuentes) {
  const body = $('#fuentesBody');
  if (!fuentes.length) { body.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-3);padding:2rem">Sin fuentes registradas</td></tr>'; return; }

  body.innerHTML = fuentes.map(f => `
    <tr class="fuente-row">
      <td><button class="toggle ${f.activa ? 'on' : ''}" onclick="toggleFuente('${f.id}', this)"></button></td>
      <td>
        <span class="fuente-name">${escHtml(f.nombre)}</span>
        <span class="fuente-url">${escHtml(f.url_base)}</span>
      </td>
      <td><span style="font-weight:600;color:var(--text-0)">${f.total_convocatorias}</span></td>
      <td><span style="font-weight:600;color:var(--green)">${f.abiertas}</span></td>
      <td><span class="cell-date">${fmtRelative(f.ultima_ejecucion)}</span></td>
      <td>
        <span class="badge ${f.activa ? 'badge-green' : 'badge-gray'}">${f.activa ? 'Activa' : 'Inactiva'}</span>
      </td>
    </tr>
  `).join('');
}

function populateFuenteFilter(fuentes) {
  const sel = $('#filterFuente');
  const current = sel.value;
  sel.innerHTML = '<option value="">Todas las fuentes</option>' + fuentes.map(f => `<option value="${f.id}">${escHtml(f.nombre)}</option>`).join('');
  sel.value = current;
}

window.toggleFuente = async function(id, btn) {
  try {
    const result = await apiFetch(`/fuentes/${id}/toggle`, { method: 'PATCH' });
    btn.classList.toggle('on', result.activa);
    toast(`${result.nombre}: ${result.activa ? 'activada' : 'desactivada'}`, 'success');
    loadFuentes();
  } catch (e) {
    toast('Error al cambiar estado', 'error');
  }
};

/* ── NOTIFICACIONES ───────────────────── */

async function loadNotificaciones() {
  try {
    const [configs, history] = await Promise.all([
      apiFetch('/config/notificaciones'),
      apiFetch('/notificaciones?limite=30'),
    ]);
    state.notifConfigs = configs;
    state.notifHistory = history;
    renderNotifConfigs(configs);
    renderNotifHistory(history);
  } catch (e) {
    toast('Error al cargar notificaciones', 'error');
  }
}

function renderNotifConfigs(configs) {
  const el = $('#notifConfigList');
  if (!configs.length) { el.innerHTML = '<p style="color:var(--text-3);font-size:0.85rem;padding:1rem 0">Sin canales configurados</p>'; return; }

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
          <button class="toggle ${c.activa ? 'on' : ''}" onclick="toggleNotifConfig('${c.id}', this)"></button>
          <button class="btn-icon-sm" onclick="deleteNotifConfig('${c.id}')" title="Eliminar">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function renderNotifHistory(history) {
  const el = $('#notifHistoryList');
  if (!history.length) { el.innerHTML = '<p style="color:var(--text-3);font-size:0.85rem;padding:1rem 0">Sin envíos registrados</p>'; return; }

  el.innerHTML = history.map(n => `
    <div class="notif-item">
      <span class="badge ${n.estado === 'ENVIADO' ? 'badge-green' : n.estado === 'ERROR' ? 'badge-red' : 'badge-gray'}" style="font-size:0.6rem">${escHtml(n.estado)}</span>
      <span class="notif-dest">${escHtml(n.destinatario)}</span>
      <span class="badge ${n.canal === 'TELEGRAM' ? 'badge-blue' : 'badge-amber'}" style="font-size:0.6rem">${escHtml(n.canal)}</span>
      <span class="notif-date">${fmtRelative(n.enviado_en)}</span>
    </div>
  `).join('');
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

window.deleteNotifConfig = async function(id) {
  if (!confirm('¿Eliminar este canal de notificación?')) return;
  try {
    await apiFetch(`/config/notificaciones/${id}`, { method: 'DELETE' });
    toast('Canal eliminado', 'success');
    loadNotificaciones();
  } catch (e) {
    toast('Error al eliminar', 'error');
  }
};

/* ── AUDIT LOG ────────────────────────── */

async function loadAudit() {
  $('#auditLoader').style.display = '';
  try {
    const nivel = $('#filterAuditNivel').value;
    const params = new URLSearchParams();
    params.set('limite', '100');
    if (nivel) params.set('nivel', nivel);
    const logs = await apiFetch(`/audit-logs?${params}`);
    state.auditLogs = logs;
    renderAudit(logs);
  } catch (e) {
    toast('Error al cargar audit log', 'error');
  } finally {
    $('#auditLoader').style.display = 'none';
  }
}

function renderAudit(logs) {
  const body = $('#auditBody');
  if (!logs.length) { body.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-3);padding:2rem">Sin registros de audit</td></tr>'; return; }

  body.innerHTML = logs.map(l => {
    const badge = l.nivel === 'ERROR' ? 'badge-red' : l.nivel === 'WARNING' ? 'badge-amber' : 'badge-green';
    return `
      <tr>
        <td><span class="badge ${badge}">${escHtml(l.nivel)}</span></td>
        <td><span style="font-family:var(--font-mono);font-size:0.78rem;color:var(--text-2)">${escHtml(l.modulo)}</span></td>
        <td><span style="max-width:400px;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(l.mensaje)}">${escHtml(l.mensaje)}</span></td>
        <td><span class="cell-fuente">${escHtml(l.fuente_nombre || '—')}</span></td>
        <td><span class="cell-date">${fmtDateTime(l.creado_en)}</span></td>
      </tr>
    `;
  }).join('');
}

/* ── FORMS ────────────────────────────── */

function setupForms() {
  const tgForm = $('#telegramForm');
  const emForm = $('#emailForm');
  const tabs = $$('#notifTypeTabs .tab');

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

/* ── INIT ─────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  setupForms();

  $$('.nav-item[data-page]').forEach(btn => {
    btn.addEventListener('click', () => navigate(btn.dataset.page));
  });

  $('#mobileMenuBtn').addEventListener('click', () => {
    $('#sidebar').classList.toggle('mobile-open');
  });

  $('#mobileToggle').addEventListener('click', () => {
    const sb = $('#sidebar');
    sb.classList.toggle('collapsed');
    document.body.classList.toggle('sidebar-collapsed');
    sb.classList.remove('mobile-open');
  });

  $('#refreshAllBtn').addEventListener('click', () => {
    const btn = $('#refreshAllBtn');
    btn.classList.add('spinning');
    loadPage(state.page);
    setTimeout(() => btn.classList.remove('spinning'), 1500);
  });

  $('#detailModalClose').addEventListener('click', () => {
    $('#detailModal').classList.remove('active');
  });

  $('#detailModal').addEventListener('click', (e) => {
    if (e.target === $('#detailModal')) $('#detailModal').classList.remove('active');
  });

  $('#filterEstado').addEventListener('change', () => { state.convOffset = 0; loadConvocatorias(); });
  $('#filterFuente').addEventListener('change', () => { state.convOffset = 0; loadConvocatorias(); });

  $('#searchInput').addEventListener('input', () => {
    clearTimeout(state.searchTimeout);
    state.searchTimeout = setTimeout(() => { state.convOffset = 0; loadConvocatorias(); }, 350);
  });

  $('#filterAuditNivel').addEventListener('change', loadAudit);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      $('#detailModal').classList.remove('active');
      $('#sidebar').classList.remove('mobile-open');
    }
  });

  navigate('dashboard');
});
