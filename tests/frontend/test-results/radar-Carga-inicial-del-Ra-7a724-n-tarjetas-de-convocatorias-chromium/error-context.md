# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: radar.spec.js >> Carga inicial del Radar >> renderiza el grid con tarjetas de convocatorias
- Location: radar.spec.js:31:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('.conv-card').first()
Expected: visible
Timeout: 10000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 10000ms
  - waiting for locator('.conv-card').first()

```

```yaml
- complementary:
  - img
  - text: GrantPulse Radar de Financiamiento
  - navigation:
    - button "Radar Activo":
      - img
      - text: Radar Activo
    - button "Instituciones":
      - img
      - text: Instituciones
    - button "Briefing":
      - img
      - text: Briefing
    - button "Sistema":
      - img
      - text: Sistema
    - button "Suscripciones":
      - img
      - text: Suscripciones
  - text: Conectado
  - button "Colapsar sidebar":
    - img
- banner:
  - button "Todas las instituciones":
    - img
    - text: Todas las instituciones
    - img
  - text: 0 activas
  - button "Actualizar datos":
    - img
- main:
  - text: 0 Activas ahora 0 Cierran en 30 días 0 Instituciones 0 Sin fecha cierre
  - img
  - textbox "Buscar por título..."
  - combobox "Ordenar por":
    - option "Por vencer primero" [selected]
    - option "Más recientes"
    - option "Última actualización"
  - combobox "Región":
    - option "Todas las regiones" [selected]
    - option "Nacional"
    - option "Arica y Parinacota"
    - option "Tarapacá"
    - option "Antofagasta"
    - option "Atacama"
    - option "Coquimbo"
    - option "Valparaíso"
    - option "Metropolitana"
    - option "O'Higgins"
    - option "Maule"
    - option "Ñuble"
    - option "Biobío"
    - option "La Araucanía"
    - option "Los Ríos"
    - option "Los Lagos"
    - option "Aysén"
    - option "Magallanes"
  - text: Solo activas 0 resultados
  - img
  - heading "Sin señal" [level=3]
  - paragraph: No hay convocatorias para los filtros seleccionados.
```

# Test source

```ts
  1   | // @ts-check
  2   | import { test, expect } from '@playwright/test';
  3   | 
  4   | const API = '/api/v1';
  5   | 
  6   | // ─── HELPERS ────────────────────────────────────────────────────────────
  7   | 
  8   | /** Espera a que el spinner desaparezca. */
  9   | async function waitForRadarReady(page) {
  10  |   await page.waitForFunction(() => {
  11  |     const loader = document.getElementById('radarLoader');
  12  |     return !loader || loader.style.display === 'none';
  13  |   });
  14  |   await page.waitForFunction(() => {
  15  |     const grid = document.getElementById('convGrid');
  16  |     return grid && (grid.children.length > 0 || document.getElementById('radarEmpty').style.display !== 'none');
  17  |   });
  18  | }
  19  | 
  20  | /** Parsea el texto de un KPI como número. */
  21  | async function kpiValue(page, id) {
  22  |   const text = await page.locator(`#${id}`).textContent();
  23  |   return parseInt(text, 10) || 0;
  24  | }
  25  | 
  26  | // ══════════════════════════════════════════════════════════════════════════
  27  | //  CARGA INICIAL DEL RADAR (datos reales desde la API)
  28  | // ══════════════════════════════════════════════════════════════════════════
  29  | 
  30  | test.describe('Carga inicial del Radar', () => {
  31  |   test('renderiza el grid con tarjetas de convocatorias', async ({ page }) => {
  32  |     await page.goto('/');
  33  |     await waitForRadarReady(page);
  34  |     const cards = page.locator('.conv-card');
> 35  |     await expect(cards.first()).toBeVisible();
      |                                 ^ Error: expect(locator).toBeVisible() failed
  36  |     await expect(cards).not.toHaveCount(0);
  37  |   });
  38  | 
  39  |   test('muestra los 4 KPIs con valores numéricos', async ({ page }) => {
  40  |     await page.goto('/');
  41  |     await waitForRadarReady(page);
  42  |     for (const id of ['kpiAbiertas', 'kpiVencen30', 'kpiInstituciones', 'kpiSinFecha']) {
  43  |       const val = await kpiValue(page, id);
  44  |       expect(val).toBeGreaterThanOrEqual(0);
  45  |     }
  46  |   });
  47  | 
  48  |   test('muestra la píldora de resultados con conteo', async ({ page }) => {
  49  |     await page.goto('/');
  50  |     await waitForRadarReady(page);
  51  |     const pill = page.locator('#activePillLabel');
  52  |     await expect(pill).toBeVisible();
  53  |     const text = await pill.textContent();
  54  |     // Puede decir "activas" o "convocatorias" según el toggle
  55  |     expect(text.length).toBeGreaterThan(0);
  56  |   });
  57  | 
  58  |   test('muestra el selector de instituciones con opciones', async ({ page }) => {
  59  |     await page.goto('/');
  60  |     await waitForRadarReady(page);
  61  |     await page.locator('#instSelectorBtn').click();
  62  |     await page.waitForTimeout(200);
  63  |     const options = page.locator('.inst-option');
  64  |     await expect(options.first()).toBeVisible();
  65  |     const count = await options.count();
  66  |     expect(count).toBeGreaterThan(1);
  67  |   });
  68  | });
  69  | 
  70  | // ══════════════════════════════════════════════════════════════════════════
  71  | //  FILTROS
  72  | // ══════════════════════════════════════════════════════════════════════════
  73  | 
  74  | test.describe('Filtros', () => {
  75  |   test('búsqueda por texto filtra resultados', async ({ page }) => {
  76  |     await page.goto('/');
  77  |     await waitForRadarReady(page);
  78  |     await page.locator('#searchInput').fill('Fondo');
  79  |     await page.waitForTimeout(600);
  80  |     await waitForRadarReady(page);
  81  |     const titles = page.locator('.conv-card-title');
  82  |     const count = await titles.count();
  83  |     // Puede que haya resultados o no, pero no debe romperse
  84  |     expect(count).toBeGreaterThanOrEqual(0);
  85  |   });
  86  | 
  87  |   test('búsqueda sin resultados muestra estado vacío', async ({ page }) => {
  88  |     await page.goto('/');
  89  |     await waitForRadarReady(page);
  90  |     await page.locator('#searchInput').fill('ZZZZNOEXISTE');
  91  |     await page.waitForTimeout(600);
  92  |     await waitForRadarReady(page);
  93  |     const emptyState = page.locator('#radarEmpty');
  94  |     // Puede estar visible si no hay resultados, o puede haber cards
  95  |     // Solo verificamos que no haya error
  96  |     const cards = page.locator('.conv-card');
  97  |     const cardCount = await cards.count();
  98  |     if (cardCount === 0) {
  99  |       await expect(emptyState).toBeVisible();
  100 |     }
  101 |   });
  102 | 
  103 |   test('selección de institución desde el dropdown', async ({ page }) => {
  104 |     await page.goto('/');
  105 |     await waitForRadarReady(page);
  106 |     // Abrir dropdown y seleccionar primera institución
  107 |     await page.locator('#instSelectorBtn').click();
  108 |     await page.waitForTimeout(300);
  109 |     // La primera opción después de "Todas" es una institución
  110 |     const options = page.locator('.inst-option');
  111 |     const count = await options.count();
  112 |     if (count > 1) {
  113 |       await options.nth(1).click({ force: true });
  114 |       await page.waitForTimeout(300);
  115 |       await waitForRadarReady(page);
  116 |       const label = page.locator('#instSelectorLabel');
  117 |       await expect(label).not.toHaveText('Todas las instituciones');
  118 |     }
  119 |   });
  120 | });
  121 | 
  122 | // ══════════════════════════════════════════════════════════════════════════
  123 | //  PAGINACIÓN
  124 | // ══════════════════════════════════════════════════════════════════════════
  125 | 
  126 | test.describe('Paginación', () => {
  127 |   test('navega a la siguiente página si existe', async ({ page }) => {
  128 |     await page.goto('/');
  129 |     await waitForRadarReady(page);
  130 |     const nextBtn = page.locator('#convPagination button:has-text("Siguiente")');
  131 |     if (await nextBtn.isEnabled()) {
  132 |       await nextBtn.click();
  133 |       await waitForRadarReady(page);
  134 |       const cards = page.locator('.conv-card');
  135 |       await expect(cards.first()).toBeVisible();
```