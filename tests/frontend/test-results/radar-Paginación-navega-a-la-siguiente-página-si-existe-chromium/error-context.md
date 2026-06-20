# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: radar.spec.js >> Paginación >> navega a la siguiente página si existe
- Location: radar.spec.js:127:3

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.isEnabled: Test timeout of 30000ms exceeded.
Call log:
  - waiting for locator('#convPagination button:has-text("Siguiente")')

```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - complementary [ref=e2]:
    - generic [ref=e3]:
      - img [ref=e5]
      - generic [ref=e7]:
        - generic [ref=e8]: GrantPulse
        - generic [ref=e9]: Radar de Financiamiento
    - navigation [ref=e10]:
      - button "Radar Activo" [ref=e11] [cursor=pointer]:
        - img [ref=e12]
        - generic [ref=e15]: Radar Activo
      - button "Instituciones" [ref=e16] [cursor=pointer]:
        - img [ref=e17]
        - generic [ref=e20]: Instituciones
      - button "Briefing" [ref=e21] [cursor=pointer]:
        - img [ref=e22]
        - generic [ref=e25]: Briefing
      - button "Sistema" [ref=e26] [cursor=pointer]:
        - img [ref=e27]
        - generic [ref=e30]: Sistema
      - button "Suscripciones" [ref=e31] [cursor=pointer]:
        - img [ref=e32]
        - generic [ref=e35]: Suscripciones
    - generic [ref=e36]:
      - generic [ref=e39]: Conectado
      - button "Colapsar sidebar" [ref=e40] [cursor=pointer]:
        - img [ref=e41]
  - generic [ref=e44]:
    - banner [ref=e45]:
      - button "Todas las instituciones" [ref=e47] [cursor=pointer]:
        - img [ref=e49]
        - generic [ref=e51]: Todas las instituciones
        - img [ref=e52]
      - generic [ref=e54]:
        - generic [ref=e57]: 0 activas
        - button "Actualizar datos" [ref=e58] [cursor=pointer]:
          - img [ref=e59]
    - main [ref=e62]:
      - generic [ref=e63]:
        - generic [ref=e64]:
          - generic [ref=e65]:
            - generic [ref=e66]: "0"
            - generic [ref=e67]: Activas ahora
          - generic [ref=e69]:
            - generic [ref=e70]: "0"
            - generic [ref=e71]: Cierran en 30 días
          - generic [ref=e73]:
            - generic [ref=e74]: "0"
            - generic [ref=e75]: Instituciones
          - generic [ref=e77]:
            - generic [ref=e78]: "0"
            - generic [ref=e79]: Sin fecha cierre
        - generic [ref=e80]:
          - generic [ref=e81]:
            - img [ref=e82]
            - textbox "Buscar por título..." [ref=e85]
          - generic [ref=e86]:
            - combobox "Ordenar por" [ref=e87] [cursor=pointer]:
              - option "Por vencer primero" [selected]
              - option "Más recientes"
              - option "Última actualización"
            - combobox "Región" [ref=e88] [cursor=pointer]:
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
            - generic [ref=e91] [cursor=pointer]: Solo activas
          - generic [ref=e92]: 0 resultados
        - generic [ref=e93]:
          - img [ref=e94]
          - heading "Sin señal" [level=3] [ref=e97]
          - paragraph [ref=e98]: No hay convocatorias para los filtros seleccionados.
```

# Test source

```ts
  31  |   test('renderiza el grid con tarjetas de convocatorias', async ({ page }) => {
  32  |     await page.goto('/');
  33  |     await waitForRadarReady(page);
  34  |     const cards = page.locator('.conv-card');
  35  |     await expect(cards.first()).toBeVisible();
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
> 131 |     if (await nextBtn.isEnabled()) {
      |                       ^ Error: locator.isEnabled: Test timeout of 30000ms exceeded.
  132 |       await nextBtn.click();
  133 |       await waitForRadarReady(page);
  134 |       const cards = page.locator('.conv-card');
  135 |       await expect(cards.first()).toBeVisible();
  136 |     } else {
  137 |       // Si no hay paginación, probar que no hay error
  138 |       test.expect(true).toBe(true);
  139 |     }
  140 |   });
  141 | });
  142 | 
  143 | // ══════════════════════════════════════════════════════════════════════════
  144 | //  MODAL DE DETALLE
  145 | // ══════════════════════════════════════════════════════════════════════════
  146 | 
  147 | test.describe('Modal de detalle', () => {
  148 |   test('abre el modal al hacer clic en una tarjeta', async ({ page }) => {
  149 |     await page.goto('/');
  150 |     await waitForRadarReady(page);
  151 |     const card = page.locator('.conv-card').first();
  152 |     await expect(card).toBeVisible();
  153 |     await card.click();
  154 |     const modal = page.locator('#detailModal');
  155 |     await expect(modal).toHaveClass(/active/);
  156 |   });
  157 | 
  158 |   test('el modal contiene información de la convocatoria', async ({ page }) => {
  159 |     await page.goto('/');
  160 |     await waitForRadarReady(page);
  161 |     await page.locator('.conv-card').first().click();
  162 |     await page.waitForTimeout(500);
  163 |     const body = page.locator('#detailModalBody');
  164 |     // Debe mostrar al menos algunos campos
  165 |     await expect(body).toContainText(/Monto|Apertura|Cierre|Historial|Descripción/i);
  166 |   });
  167 | 
  168 |   test('cierra el modal con Escape', async ({ page }) => {
  169 |     await page.goto('/');
  170 |     await waitForRadarReady(page);
  171 |     await page.locator('.conv-card').first().click();
  172 |     await expect(page.locator('#detailModal')).toHaveClass(/active/);
  173 |     await page.keyboard.press('Escape');
  174 |     await expect(page.locator('#detailModal')).not.toHaveClass(/active/);
  175 |   });
  176 | });
  177 | 
  178 | // ══════════════════════════════════════════════════════════════════════════
  179 | //  NAVEGACIÓN ENTRE PÁGINAS
  180 | // ══════════════════════════════════════════════════════════════════════════
  181 | 
  182 | test.describe('Navegación', () => {
  183 |   test('navega a Instituciones', async ({ page }) => {
  184 |     await page.goto('/');
  185 |     await page.waitForLoadState('networkidle');
  186 |     await page.locator('.nav-item[data-page="instituciones"]').click();
  187 |     await page.waitForTimeout(500);
  188 |     const instCards = page.locator('.inst-card');
  189 |     await expect(instCards.first()).toBeVisible();
  190 |   });
  191 | 
  192 |   test('navega a Briefing', async ({ page }) => {
  193 |     await page.goto('/');
  194 |     await page.waitForLoadState('networkidle');
  195 |     await page.locator('.nav-item[data-page="briefing"]').click();
  196 |     await page.waitForTimeout(500);
  197 |     // Puede mostrar tabla o estado vacío
  198 |     const sections = page.locator('.briefing-section');
  199 |     const empty = page.locator('.empty-state');
  200 |     const hasContent = (await sections.count()) > 0;
  201 |     const hasEmpty = (await empty.count()) > 0;
  202 |     expect(hasContent || hasEmpty).toBe(true);
  203 |   });
  204 | 
  205 |   test('navega a Admin y sus tabs funcionan', async ({ page }) => {
  206 |     await page.goto('/');
  207 |     await page.waitForLoadState('networkidle');
  208 |     await page.locator('.nav-item[data-page="admin"]').click();
  209 |     await page.waitForTimeout(500);
  210 |     for (const tab of ['fuentes', 'notificaciones', 'audit']) {
  211 |       await page.locator(`.admin-tab[data-tab="${tab}"]`).click();
  212 |       await page.waitForTimeout(300);
  213 |       await expect(page.locator(`#adminpane-${tab}`)).toHaveClass(/active/);
  214 |     }
  215 |   });
  216 | });
  217 | 
  218 | // ══════════════════════════════════════════════════════════════════════════
  219 | //  RESPONSIVE
  220 | // ══════════════════════════════════════════════════════════════════════════
  221 | 
  222 | test.describe('Responsive y sidebar', () => {
  223 |   test('sidebar se puede colapsar/expandir', async ({ page }) => {
  224 |     await page.goto('/');
  225 |     await page.locator('#sidebarToggle').click();
  226 |     await expect(page.locator('#sidebar')).toHaveClass(/collapsed/);
  227 |     await page.locator('#sidebarToggle').click();
  228 |     await expect(page.locator('#sidebar')).not.toHaveClass(/collapsed/);
  229 |   });
  230 | 
  231 |   test('viewport mobile muestra menú', async ({ page }) => {
```