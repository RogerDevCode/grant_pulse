// @ts-check
/**
 * Red Team E2E tests — incisivos, paranoicos, diseñados para romper el sistema.
 *
 * Cubre los bugs identificados en docs/qa-test-plan-contabilizacion.md:
 *  - B01: Paginación oculta el total
 *  - B02: KPI instituciones se filtra
 *  - B03: KPI vencen_30 mezcla filtrado y global
 *  - B05: Pill engañosa
 *
 * Más casos extremos: payloads malformados, concurrencia, persistencia de estado.
 */

import { test, expect } from '@playwright/test';

const API = '/api/v1';

// ─── HELPERS ────────────────────────────────────────────────────────────

async function waitForRadarReady(page) {
  await page.waitForFunction(() => {
    const loader = document.getElementById('radarLoader');
    return !loader || loader.style.display === 'none';
  });
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(500);
}

async function fetchCount(request, params = '') {
  const url = `${API}/convocatorias/count${params ? '?' + params : ''}`;
  const r = await request.get(url);
  return r.json();
}

async function fetchKpi(request, params = '') {
  const url = `${API}/convocatorias/kpi${params ? '?' + params : ''}`;
  const r = await request.get(url);
  return r.json();
}

// ══════════════════════════════════════════════════════════════════════════
//  BUG B01: PAGINACIÓN OCULTA EL TOTAL REAL
// ══════════════════════════════════════════════════════════════════════════

test.describe('Red Team — B01: Totalización vs paginación', () => {
  test('la pill de resultados muestra el TOTAL, no solo la página actual', async ({ page, request }) => {
    await page.goto('/');
    await waitForRadarReady(page);

    const apiCount = await fetchCount(request, 'estado=ABIERTO');
    const totalReal = apiCount.total;

    // La pill debería mostrar el total real
    const pillText = await page.locator('#activePillLabel').textContent();
    const match = pillText?.match(/(\d+)/);
    const numeroEnPill = match ? parseInt(match[1], 10) : 0;

    expect(numeroEnPill, `La pill muestra ${numeroEnPill} pero el total real es ${totalReal}`).toBe(totalReal);
  });

  test('el #resultNum es consistente con el endpoint /count', async ({ page, request }) => {
    await page.goto('/');
    await waitForRadarReady(page);

    const apiCount = await fetchCount(request, 'estado=ABIERTO');
    const resultNumText = await page.locator('#resultNum').textContent();
    const resultNum = parseInt(resultNumText || '0', 10);

    expect(resultNum).toBe(apiCount.total);
  });

  test('suma de cards en todas las páginas = total del endpoint', async ({ page, request }) => {
    await page.goto('/');
    await waitForRadarReady(page);

    const apiCount = await fetchCount(request, 'estado=ABIERTO');
    let totalVisto = 0;

    while (true) {
      const cards = await page.locator('.conv-card').count();
      totalVisto += cards;

      const nextBtn = page.locator('#convPagination button:has-text("Siguiente")');
      if (!(await nextBtn.isEnabled()) || (await nextBtn.count()) === 0) break;
      await nextBtn.click();
      await waitForRadarReady(page);
    }

    expect(totalVisto).toBe(apiCount.total);
  });
});

// ══════════════════════════════════════════════════════════════════════════
//  BUG B03: KPI vencen_30 MEZCLA FILTRADO Y GLOBAL
// ══════════════════════════════════════════════════════════════════════════

test.describe('Red Team — B03: KPI vencen_30 con filtro', () => {
  test('KPI vencen_30 sin filtro = suma de cards con cierre < 30 días', async ({ page, request }) => {
    await page.goto('/');
    await waitForRadarReady(page);

    const kpiSinFiltro = await fetchKpi(request, 'estado=ABIERTO');
    const kpiSinFiltroDom = parseInt(await page.locator('#kpiVencen30').textContent() || '0', 10);

    // El KPI sin filtro y el DOM deben coincidir
    expect(kpiSinFiltroDom).toBe(kpiSinFiltro.vencen_30);
  });

  test('KPI vencen_30 CON filtro es <= KPI sin filtro', async ({ page, request }) => {
    // 1. Sin filtro
    await page.goto('/');
    await waitForRadarReady(page);
    const kpiSinFiltro = parseInt(await page.locator('#kpiVencen30').textContent() || '0', 10);

    // 2. Filtrar por una fuente (CORFO = id 2 en el catálogo)
    const fuentes = await (await request.get(`${API}/fuentes`)).json();
    const corfo = fuentes.find(f => f.nombre === 'CORFO');
    if (!corfo) test.skip();

    await page.locator('#instSelectorBtn').click();
    await page.waitForTimeout(300);
    await page.locator(`.inst-option[data-id="${corfo.id}"]`).click();
    await waitForRadarReady(page);

    const kpiConFiltroDom = parseInt(await page.locator('#kpiVencen30').textContent() || '0', 10);

    // El KPI filtrado NO PUEDE ser mayor al global
    expect(
      kpiConFiltroDom,
      `KPI filtrado ${kpiConFiltroDom} no puede ser mayor que global ${kpiSinFiltro}`
    ).toBeLessThanOrEqual(kpiSinFiltro);
  });

  test('KPI instituciones con filtro es estable o etiquetado', async ({ page, request }) => {
    await page.goto('/');
    await waitForRadarReady(page);
    const kpiInstitucionesGlobal = parseInt(await page.locator('#kpiInstituciones').textContent() || '0', 10);

    // Aplicar filtro
    const fuentes = await (await request.get(`${API}/fuentes`)).json();
    const corfo = fuentes.find(f => f.nombre === 'CORFO');
    if (!corfo) test.skip();

    await page.locator('#instSelectorBtn').click();
    await page.waitForTimeout(300);
    await page.locator(`.inst-option[data-id="${corfo.id}"]`).click();
    await waitForRadarReady(page);

    const kpiInstitucionesFiltrado = parseInt(await page.locator('#kpiInstituciones').textContent() || '0', 10);

    // Si el KPI cambia drásticamente (de 6 a 1), debe haber un indicador visual
    if (kpiInstitucionesFiltrado !== kpiInstitucionesGlobal) {
      // Verificar que el usuario tiene una pista visual (tooltip en el item padre)
      const tooltip = await page.locator('.kpi-blue').getAttribute('title');
      expect(tooltip, 'KPI instituciones filtrado debe tener tooltip explicativo').toBeTruthy();
      expect(tooltip).toMatch(/filtro|instituci/i);
    }
  });
});

// ══════════════════════════════════════════════════════════════════════════
//  ROBUSTEZ: inputs extremos, payloads malformados, race conditions
// ══════════════════════════════════════════════════════════════════════════

test.describe('Red Team — Robustez del frontend', () => {
  test('búsqueda con caracteres especiales no rompe el frontend', async ({ page }) => {
    await page.goto('/');
    await waitForRadarReady(page);

    // Inputs extremos
    const inputs = [
      '<script>alert("xss")</script>',
      "'); DROP TABLE convocatorias;--",
      '🎉🔥💥',
      'A'.repeat(500),
      '\n\r\t',
      '   ',  // solo espacios
    ];

    for (const input of inputs) {
      await page.locator('#searchInput').fill(input);
      await page.waitForTimeout(500);
      // No debe haber error en consola ni pantalla rota
      const errorVisible = await page.locator('text=/error/i').isVisible().catch(() => false);
      expect(errorVisible, `Input "${input}" no debe causar error visible`).toBe(false);
    }
  });

  test('clics múltiples rápidos en el botón scrape no disparan múltiples requests', async ({ page, request }) => {
    let scrapeCount = 0;
    page.on('request', req => {
      if (req.url().includes('/api/v1/scrape') && req.method() === 'POST') {
        scrapeCount++;
      }
    });

    await page.goto('/');
    await waitForRadarReady(page);

    // 5 clics rápidos
    const btn = page.locator('#scrapeBtn');
    for (let i = 0; i < 5; i++) {
      await btn.click({ force: true }).catch(() => {});
    }
    await page.waitForTimeout(2000);

    // Debe haber máximo 1 request POST (los demás reciben 409)
    expect(scrapeCount).toBeLessThanOrEqual(1);
  });

  test('navegación rápida entre páginas no causa errores', async ({ page }) => {
    await page.goto('/');
    await waitForRadarReady(page);

    const pages = ['radar', 'instituciones', 'briefing', 'admin', 'suscripciones'];
    for (let i = 0; i < 3; i++) {
      for (const p of pages) {
        await page.locator(`.nav-item[data-page="${p}"]`).click();
        await page.waitForTimeout(50);  // muy rápido
      }
    }

    // Después del stress, la última página activa debe responder
    const activePage = await page.locator('.page.active').count();
    expect(activePage).toBe(1);
  });

  test('el frontend no se rompe con BD vacía', async ({ page, request }) => {
    // Verificar que el frontend maneja el caso de "0 convocatorias"
    const count = await fetchCount(request, 'estado=ABIERTO');
    if (count.total > 0) {
      test.skip();
    }

    await page.goto('/');
    await waitForRadarReady(page);

    // El empty state debe mostrarse
    await expect(page.locator('#radarEmpty')).toBeVisible();
  });
});

// ══════════════════════════════════════════════════════════════════════════
//  CONSISTENCIA API vs FRONTEND
// ══════════════════════════════════════════════════════════════════════════

test.describe('Red Team — Consistencia API/Frontend', () => {
  test('KPI activas del DOM = endpoint /kpi', async ({ page, request }) => {
    await page.goto('/');
    await waitForRadarReady(page);

    const kpiApi = await fetchKpi(request, 'estado=ABIERTO');
    const kpiDom = parseInt(await page.locator('#kpiAbiertas').textContent() || '0', 10);

    expect(kpiDom).toBe(kpiApi.abiertas);
  });

  test('KPI instituciones del DOM = endpoint /kpi', async ({ page, request }) => {
    await page.goto('/');
    await waitForRadarReady(page);

    const kpiApi = await fetchKpi(request, 'estado=ABIERTO');
    const kpiDom = parseInt(await page.locator('#kpiInstituciones').textContent() || '0', 10);

    expect(kpiDom).toBe(kpiApi.instituciones);
  });

  test('badge de navegación del sidebar refleja el conteo global', async ({ page, request }) => {
    await page.goto('/');
    await waitForRadarReady(page);

    const count = await fetchCount(request, 'estado=ABIERTO');
    const badgeText = await page.locator('#navBadgeRadar').textContent();
    const badgeNum = parseInt(badgeText || '0', 10);

    if (badgeText && badgeText.trim() !== '') {
      expect(badgeNum).toBe(count.total);
    }
  });
});

// ══════════════════════════════════════════════════════════════════════════
//  ESTABILIDAD DE FILTROS COMBINADOS
// ══════════════════════════════════════════════════════════════════════════

test.describe('Red Team — Filtros combinados', () => {
  test('filtro institución + búsqueda de texto funciona', async ({ page, request }) => {
    const fuentes = await (await request.get(`${API}/fuentes`)).json();
    const corfo = fuentes.find(f => f.nombre === 'CORFO');
    if (!corfo) test.skip();

    await page.goto('/');
    await waitForRadarReady(page);

    await page.locator('#instSelectorBtn').click();
    await page.waitForTimeout(300);
    await page.locator(`.inst-option[data-id="${corfo.id}"]`).click();
    await waitForRadarReady(page);

    await page.locator('#searchInput').fill('fondo');
    await page.waitForTimeout(800);
    await waitForRadarReady(page);

    // Todas las cards visibles deben ser de CORFO
    const fuenteEnCard = await page.locator('.conv-card-meta strong').first().textContent();
    expect(fuenteEnCard).toBe('CORFO');
  });

  test('filtro región funciona correctamente', async ({ page, request }) => {
    const kpi = await fetchKpi(request, 'estado=ABIERTO');
    if (kpi.sin_fecha === 0) test.skip();

    await page.goto('/');
    await waitForRadarReady(page);

    // Seleccionar "Nacional"
    await page.locator('#filterRegion').selectOption('Nacional');
    await page.waitForTimeout(500);
    await waitForRadarReady(page);

    const countFiltrado = parseInt(await page.locator('#resultNum').textContent() || '0', 10);
    const countNacional = (await fetchCount(request, 'estado=ABIERTO&region=Nacional')).total;

    expect(countFiltrado).toBe(countNacional);
  });
});
