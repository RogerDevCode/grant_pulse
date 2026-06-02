/**
 * GrantPulse Frontend - Lógica de cliente en Vanilla JS
 */

const API_BASE_URL = '/api/v1';

// Estado global de la aplicación
let state = {
    convocatorias: [],
    filterStatus: ''
};

// Referencias a elementos del DOM
const grantsContainer = document.getElementById('grantsContainer');
const statusFilter = document.getElementById('statusFilter');
const refreshBtn = document.getElementById('refreshBtn');
const historyModal = document.getElementById('historyModal');
const closeModalBtn = document.getElementById('closeModalBtn');
const historyContainer = document.getElementById('historyContainer');
const modalTitle = document.getElementById('modalTitle');

// Navegación
const navGrants = document.getElementById('navGrants');
const navConfig = document.getElementById('navConfig');
const grantsPage = document.getElementById('grantsPage');
const configPage = document.getElementById('configPage');

// Configuración
const telegramForm = document.getElementById('telegramForm');
const telegramList = document.getElementById('telegramList');
const emailForm = document.getElementById('emailForm');
const emailList = document.getElementById('emailList');

/**
 * Inicialización
 */
document.addEventListener('DOMContentLoaded', () => {
    fetchGrants();
    fetchConfigs();

    // Navegación
    navGrants.addEventListener('click', () => {
        navGrants.classList.add('active');
        navConfig.classList.remove('active');
        grantsPage.classList.remove('hidden');
        configPage.classList.add('hidden');
    });

    navConfig.addEventListener('click', () => {
        navConfig.classList.add('active');
        navGrants.classList.remove('active');
        configPage.classList.remove('hidden');
        grantsPage.classList.add('hidden');
    });

    // Event Listeners
    statusFilter.addEventListener('change', (e) => {
        state.filterStatus = e.target.value;
        renderGrants();
    });

    refreshBtn.addEventListener('click', () => {
        fetchGrants();
    });

    closeModalBtn.addEventListener('click', () => {
        historyModal.classList.remove('active');
    });

    historyModal.addEventListener('click', (e) => {
        if (e.target === historyModal) {
            historyModal.classList.remove('active');
        }
    });

    // Formulario de Telegram
    telegramForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const data = {
            nombre: document.getElementById('tgNombre').value,
            tipo: "TELEGRAM",
            configuracion: {
                token: document.getElementById('tgToken').value,
                chat_id: document.getElementById('tgChatId').value
            },
            activa: true
        };

        try {
            const response = await fetch(`${API_BASE_URL}/config/notificaciones`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            if (!response.ok) throw new Error('Error al guardar configuración');
            
            telegramForm.reset();
            fetchConfigs();
        } catch (error) {
            alert('Error al guardar el canal de Telegram');
        }
    });

    // Formulario de Email
    emailForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const targets = document.getElementById('emTargets').value.split(',').map(t => t.trim()).filter(t => t);
        const data = {
            nombre: document.getElementById('emNombre').value,
            tipo: "EMAIL",
            configuracion: {
                host: document.getElementById('emHost').value,
                port: parseInt(document.getElementById('emPort').value),
                user: document.getElementById('emUser').value,
                password: document.getElementById('emPass').value,
                from_email: document.getElementById('emFrom').value,
                target_emails: targets,
                use_tls: true
            },
            activa: true
        };

        try {
            const response = await fetch(`${API_BASE_URL}/config/notificaciones`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            if (!response.ok) throw new Error();
            
            emailForm.reset();
            document.getElementById('emPort').value = 587;
            fetchConfigs();
        } catch (error) {
            alert('Error al guardar el canal de Email');
        }
    });
});

/**
 * Obtiene las configuraciones de notificación
 */
async function fetchConfigs() {
    telegramList.innerHTML = '<div class="loader">Cargando canales...</div>';
    emailList.innerHTML = '<div class="loader">Cargando canales...</div>';
    try {
        const response = await fetch(`${API_BASE_URL}/config/notificaciones`);
        if (!response.ok) throw new Error();
        const configs = await response.json();
        renderConfigs(configs);
    } catch (error) {
        telegramList.innerHTML = '<p>Error al cargar configuraciones.</p>';
        emailList.innerHTML = '<p>Error al cargar configuraciones.</p>';
    }
}

/**
 * Renderiza la lista de canales configurados
 */
function renderConfigs(configs) {
    const tgs = configs.filter(c => c.tipo === 'TELEGRAM');
    const ems = configs.filter(c => c.tipo === 'EMAIL');

    if (tgs.length === 0) {
        telegramList.innerHTML = '<p style="color: var(--text-muted); font-style: italic;">No hay canales configurados aún.</p>';
    } else {
        telegramList.innerHTML = tgs.map(c => `
            <div class="config-item">
                <div class="config-info">
                    <h3>${c.nombre}</h3>
                    <p>Chat ID: ${c.configuracion.chat_id} | Token: ****${c.configuracion.token.slice(-4)}</p>
                </div>
                <button class="btn-delete" onclick="deleteConfig('${c.id}')">Eliminar</button>
            </div>
        `).join('');
    }

    if (ems.length === 0) {
        emailList.innerHTML = '<p style="color: var(--text-muted); font-style: italic;">No hay canales configurados aún.</p>';
    } else {
        emailList.innerHTML = ems.map(c => `
            <div class="config-item">
                <div class="config-info">
                    <h3>${c.nombre}</h3>
                    <p>Host: ${c.configuracion.host} | Destinatarios: ${c.configuracion.target_emails.join(', ')}</p>
                </div>
                <button class="btn-delete" onclick="deleteConfig('${c.id}')">Eliminar</button>
            </div>
        `).join('');
    }
}

/**
 * Elimina una configuración
 */
async function deleteConfig(id) {
    if (!confirm('¿Seguro que deseas eliminar este canal?')) return;
    try {
        const response = await fetch(`${API_BASE_URL}/config/notificaciones/${id}`, { method: 'DELETE' });
        if (!response.ok) throw new Error();
        fetchConfigs();
    } catch (error) {
        alert('Error al eliminar');
    }
}

/**
 * Obtiene las convocatorias desde la API
 */
async function fetchGrants() {
    grantsContainer.innerHTML = '<div class="loader">Cargando convocatorias...</div>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/convocatorias`);
        if (!response.ok) throw new Error('Error al obtener datos de la API');
        
        state.convocatorias = await response.json();
        renderGrants();
    } catch (error) {
        console.error(error);
        grantsContainer.innerHTML = `<div class="loader" style="color: var(--danger)">Error: No se pudo conectar con el servidor.</div>`;
    }
}

/**
 * Renderiza las tarjetas de convocatorias en el grid
 */
function renderGrants() {
    const filtered = state.filterStatus 
        ? state.convocatorias.filter(c => c.estado.toUpperCase() === state.filterStatus)
        : state.convocatorias;

    if (filtered.length === 0) {
        grantsContainer.innerHTML = '<div class="loader">No se encontraron convocatorias.</div>';
        return;
    }

    grantsContainer.innerHTML = filtered.map(grant => `
        <article class="grant-card">
            <header class="grant-header">
                <span class="status-badge status-${grant.estado.toLowerCase()}">${grant.estado}</span>
            </header>
            <h2 class="grant-title">${grant.titulo}</h2>
            <p class="grant-desc">${grant.descripcion || 'Sin descripción disponible.'}</p>
            
            <div class="grant-meta">
                ${grant.monto ? `<div><strong>Monto:</strong> ${formatCurrency(grant.monto)}</div>` : ''}
                ${grant.fecha_cierre ? `<div><strong>Cierre:</strong> ${new Date(grant.fecha_cierre).toLocaleDateString()}</div>` : ''}
                <div><strong>Actualizado:</strong> ${new Date(grant.actualizado_en).toLocaleString()}</div>
            </div>

            <div class="grant-actions">
                <a href="${grant.url_detalle}" target="_blank" rel="noopener" class="btn-link">Ver en Portal</a>
                <button onclick="viewHistory('${grant.id}', '${grant.titulo}')" class="btn-outline">Historial</button>
            </div>
        </article>
    `).join('');
}

/**
 * Obtiene y muestra el historial de cambios de una convocatoria específica
 */
async function viewHistory(id, title) {
    modalTitle.textContent = `Historial: ${title}`;
    historyContainer.innerHTML = '<div class="loader">Cargando cambios...</div>';
    historyModal.classList.add('active');

    try {
        const response = await fetch(`${API_BASE_URL}/convocatorias/${id}`);
        if (!response.ok) throw new Error('Error al obtener historial');
        
        const data = await response.json();
        const history = data.historial_cambios;

        if (history.length === 0) {
            historyContainer.innerHTML = '<p>No se registran cambios relevantes aún.</p>';
            return;
        }

        historyContainer.innerHTML = history.map(event => `
            <div class="event-card">
                <div class="event-date">${new Date(event.fecha_deteccion).toLocaleString()}</div>
                <div class="event-type">${event.tipo} ${event.es_relevante ? '⭐' : ''}</div>
                <div class="event-deltas">
                    ${event.deltas.map(d => `
                        <div class="delta-item">
                            <strong>${translateField(d.campo)}:</strong> 
                            <span style="color: var(--danger)">${d.valor_anterior || 'N/A'}</span> 
                            &rarr; 
                            <span style="color: var(--success)">${d.valor_nuevo || 'N/A'}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `).join('');

    } catch (error) {
        historyContainer.innerHTML = '<p style="color: var(--danger)">Error al cargar el historial.</p>';
    }
}

/**
 * Helpers
 */
function formatCurrency(val) {
    return new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(val);
}

function translateField(field) {
    const map = {
        'estado': 'Estado',
        'fecha_cierre': 'Fecha de Cierre',
        'monto': 'Monto Máximo',
        'titulo': 'Título',
        'descripcion': 'Descripción',
        'url_detalle': 'Enlace'
    };
    return map[field] || field;
}

window.deleteConfig = deleteConfig;
window.viewHistory = viewHistory;
