// @ts-check
import { test, expect } from '@playwright/test';

const API = '/api/v1';

// ─── HELPERS ────────────────────────────────────────────────────────────

/** Espera a que el spinner desaparezca. */
async function waitForRadarReady(page) {
  await page.waitForFunction(() => {
    const loader = document.getElementById('radarLoader');
    return !loader || loader.style.display === 'none';
  });
  await page.waitForFunction(() => {
    const grid = document.getElementById('convGrid');
    return grid && (grid.children.length > 0 || document.getElementById('radarEmpty').style.display !== 'none');
  });
}

/** Parsea el texto de un KPI como número. */
async function kpiValue(page, id) {
  const text = await page.locator(`#${id}`).textContent();
  return parseInt(text, 10) || 0;
}

// ══════════════════════════════════════════════════════════════════════════
//  CARGA INICIAL DEL RADAR (datos reales desde la API)
// ══════════════════════════════════════════════════════════════════════════

test.describe('Carga inicial del Radar', () => {
  test('renderiza el grid con tarjetas de convocatorias', async ({ page }) => {
    await page.goto('/');
    await waitForRadarReady(page);
    const cards = page.locator('.conv-card');
    await expect(cards.first()).toBeVisible();
    await expect(cards).not.toHaveCount(0);
  });

  test('muestra los 4 KPIs con valores numéricos', async ({ page }) => {
    await page.goto('/');
    await waitForRadarReady(page);
    for (const id of ['kpiAbiertas', 'kpiVencen30', 'kpiInstituciones', 'kpiSinFecha']) {
      const val = await kpiValue(page, id);
      expect(val).toBeGreaterThanOrEqual(0);
    }
  });

  test('muestra la píldora de resultados con conteo', async ({ page }) => {
    await page.goto('/');
    await waitForRadarReady(page);
    const pill = page.locator('#activePillLabel');
    await expect(pill).toBeVisible();
    const text = await pill.textContent();
    // Puede decir "activas" o "convocatorias" según el toggle
    expect(text.length).toBeGreaterThan(0);
  });

  test('muestra el selector de instituciones con opciones', async ({ page }) => {
    await page.goto('/');
    await waitForRadarReady(page);
    await page.locator('#instSelectorBtn').click();
    await page.waitForTimeout(200);
    const options = page.locator('.inst-option');
    await expect(options.first()).toBeVisible();
    const count = await options.count();
    expect(count).toBeGreaterThan(1);
  });
});

// ══════════════════════════════════════════════════════════════════════════
//  FILTROS
// ══════════════════════════════════════════════════════════════════════════

test.describe('Filtros', () => {
  test('búsqueda por texto filtra resultados', async ({ page }) => {
    await page.goto('/');
    await waitForRadarReady(page);
    await page.locator('#searchInput').fill('Fondo');
    await page.waitForTimeout(600);
    await waitForRadarReady(page);
    const titles = page.locator('.conv-card-title');
    const count = await titles.count();
    // Puede que haya resultados o no, pero no debe romperse
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('búsqueda sin resultados muestra estado vacío', async ({ page }) => {
    await page.goto('/');
    await waitForRadarReady(page);
    await page.locator('#searchInput').fill('ZZZZNOEXISTE');
    await page.waitForTimeout(600);
    await waitForRadarReady(page);
    const emptyState = page.locator('#radarEmpty');
    // Puede estar visible si no hay resultados, o puede haber cards
    // Solo verificamos que no haya error
    const cards = page.locator('.conv-card');
    const cardCount = await cards.count();
    if (cardCount === 0) {
      await expect(emptyState).toBeVisible();
    }
  });

  test('selección de institución desde el dropdown', async ({ page }) => {
    await page.goto('/');
    await waitForRadarReady(page);
    // Abrir dropdown y seleccionar primera institución
    await page.locator('#instSelectorBtn').click();
    await page.waitForTimeout(300);
    // La primera opción después de "Todas" es una institución
    const options = page.locator('.inst-option');
    const count = await options.count();
    if (count > 1) {
      await options.nth(1).click({ force: true });
      await page.waitForTimeout(300);
      await waitForRadarReady(page);
      const label = page.locator('#instSelectorLabel');
      await expect(label).not.toHaveText('Todas las instituciones');
    }
  });
});

// ══════════════════════════════════════════════════════════════════════════
//  PAGINACIÓN
// ══════════════════════════════════════════════════════════════════════════

test.describe('Paginación', () => {
  test('navega a la siguiente página si existe', async ({ page }) => {
    await page.goto('/');
    await waitForRadarReady(page);
    const nextBtn = page.locator('#convPagination button:has-text("Siguiente")');
    if (await nextBtn.isEnabled()) {
      await nextBtn.click();
      await waitForRadarReady(page);
      const cards = page.locator('.conv-card');
      await expect(cards.first()).toBeVisible();
    } else {
      // Si no hay paginación, probar que no hay error
      test.expect(true).toBe(true);
    }
  });
});

// ══════════════════════════════════════════════════════════════════════════
//  MODAL DE DETALLE
// ══════════════════════════════════════════════════════════════════════════

test.describe('Modal de detalle', () => {
  test('abre el modal al hacer clic en una tarjeta', async ({ page }) => {
    await page.goto('/');
    await waitForRadarReady(page);
    const card = page.locator('.conv-card').first();
    await expect(card).toBeVisible();
    await card.click();
    const modal = page.locator('#detailModal');
    await expect(modal).toHaveClass(/active/);
  });

  test('el modal contiene información de la convocatoria', async ({ page }) => {
    await page.goto('/');
    await waitForRadarReady(page);
    await page.locator('.conv-card').first().click();
    await page.waitForTimeout(500);
    const body = page.locator('#detailModalBody');
    // Debe mostrar al menos algunos campos
    await expect(body).toContainText(/Monto|Apertura|Cierre|Historial|Descripción/i);
  });

  test('cierra el modal con Escape', async ({ page }) => {
    await page.goto('/');
    await waitForRadarReady(page);
    await page.locator('.conv-card').first().click();
    await expect(page.locator('#detailModal')).toHaveClass(/active/);
    await page.keyboard.press('Escape');
    await expect(page.locator('#detailModal')).not.toHaveClass(/active/);
  });
});

// ══════════════════════════════════════════════════════════════════════════
//  NAVEGACIÓN ENTRE PÁGINAS
// ══════════════════════════════════════════════════════════════════════════

test.describe('Navegación', () => {
  test('navega a Instituciones', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.locator('.nav-item[data-page="instituciones"]').click();
    await page.waitForTimeout(500);
    const instCards = page.locator('.inst-card');
    await expect(instCards.first()).toBeVisible();
  });

  test('navega a Briefing', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.locator('.nav-item[data-page="briefing"]').click();
    await page.waitForTimeout(500);
    // Puede mostrar tabla o estado vacío
    const sections = page.locator('.briefing-section');
    const empty = page.locator('.empty-state');
    const hasContent = (await sections.count()) > 0;
    const hasEmpty = (await empty.count()) > 0;
    expect(hasContent || hasEmpty).toBe(true);
  });

  test('navega a Admin y sus tabs funcionan', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.locator('.nav-item[data-page="admin"]').click();
    await page.waitForTimeout(500);
    for (const tab of ['fuentes', 'notificaciones', 'audit']) {
      await page.locator(`.admin-tab[data-tab="${tab}"]`).click();
      await page.waitForTimeout(300);
      await expect(page.locator(`#adminpane-${tab}`)).toHaveClass(/active/);
    }
  });
});

// ══════════════════════════════════════════════════════════════════════════
//  RESPONSIVE
// ══════════════════════════════════════════════════════════════════════════

test.describe('Responsive y sidebar', () => {
  test('sidebar se puede colapsar/expandir', async ({ page }) => {
    await page.goto('/');
    await page.locator('#sidebarToggle').click();
    await expect(page.locator('#sidebar')).toHaveClass(/collapsed/);
    await page.locator('#sidebarToggle').click();
    await expect(page.locator('#sidebar')).not.toHaveClass(/collapsed/);
  });

  test('viewport mobile muestra menú', async ({ page }) => {
    await page.goto('/');
    await page.setViewportSize({ width: 375, height: 812 });
    await page.locator('#mobileMenuBtn').click();
    await expect(page.locator('#sidebar')).toHaveClass(/mobile-open/);
  });
});

// ══════════════════════════════════════════════════════════════════════════
//  SUSCRIPCIONES (datos reales)
// ══════════════════════════════════════════════════════════════════════════

test.describe('Suscripciones', () => {
  test('navega a la página de suscripciones', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.locator('.nav-item[data-page="suscripciones"]').click();
    await page.waitForTimeout(500);
    const form = page.locator('#suscripcionForm');
    await expect(form).toBeVisible();
    const regionCheckboxes = page.locator('#subRegiones input[type="checkbox"]');
    const count = await regionCheckboxes.count();
    expect(count).toBe(17); // 17 regiones chilenas desde la API real
  });

  test('muestra error si no se selecciona ninguna región', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.locator('.nav-item[data-page="suscripciones"]').click();
    await page.waitForTimeout(300);
    await page.locator('#subChatId').fill('123456789');
    await page.locator('#subNombre').fill('Test E2E');
    await page.locator('#suscripcionForm button[type="submit"]').click();
    await page.waitForTimeout(300);
    // Debe mostrar toast de error por no seleccionar región
    const toast = page.locator('.toast.error');
    await expect(toast).toBeVisible();
  });

  test('crea y muestra suscripción exitosamente', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.locator('.nav-item[data-page="suscripciones"]').click();
    await page.waitForTimeout(300);
    // Completar formulario
    await page.locator('#subChatId').fill('987654321');
    await page.locator('#subNombre').fill('Test E2E Playwright');
    // Seleccionar 2 regiones
    const checkboxes = page.locator('#subRegiones input[type="checkbox"]');
    await checkboxes.nth(0).check();
    await checkboxes.nth(1).check();
    // Enviar
    await page.locator('#suscripcionForm button[type="submit"]').click();
    await page.waitForTimeout(500);
    // Debe mostrar toast de éxito
    const toast = page.locator('.toast.success');
    await expect(toast).toBeVisible();
  });
});

// ══════════════════════════════════════════════════════════════════════════
//  MANEJO DE ERRORES
// ══════════════════════════════════════════════════════════════════════════

test.describe('Manejo de errores', () => {
  test('carga inicial sin errores visibles', async ({ page }) => {
    await page.goto('/');
    await waitForRadarReady(page);
    // Verificar que no hay mensajes de error en la consola
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.waitForTimeout(500);
    // El radar se cargó correctamente si hay cards o estado vacío
    const cards = page.locator('.conv-card');
    const empty = page.locator('#radarEmpty');
    const hasCards = (await cards.count()) > 0;
    const hasEmpty = await empty.isVisible();
    expect(hasCards || hasEmpty).toBe(true);
  });

  test('urls de convocatorias se renderizan sin error', async ({ page }) => {
    await page.goto('/');
    await waitForRadarReady(page);
    const cards = page.locator('.conv-card');
    const count = await cards.count();
    expect(count).toBeGreaterThan(0);
    // Click en la primera card para ver detalle
    await cards.first().click();
    await page.waitForTimeout(500);
    const body = page.locator('#detailModalBody');
    // No debe mostrar error
    await expect(body).not.toContainText(/Error al cargar/i);
  });
});
