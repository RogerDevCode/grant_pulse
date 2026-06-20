# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: radar.spec.js >> Modal de detalle >> abre el modal al hacer clic en una tarjeta
- Location: radar.spec.js:148:3

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
> 152 |     await expect(card).toBeVisible();
      |                        ^ Error: expect(locator).toBeVisible() failed
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
  232 |     await page.goto('/');
  233 |     await page.setViewportSize({ width: 375, height: 812 });
  234 |     await page.locator('#mobileMenuBtn').click();
  235 |     await expect(page.locator('#sidebar')).toHaveClass(/mobile-open/);
  236 |   });
  237 | });
  238 | 
  239 | // ══════════════════════════════════════════════════════════════════════════
  240 | //  SUSCRIPCIONES (datos reales — tests autocontenidos)
  241 | // ══════════════════════════════════════════════════════════════════════════
  242 | 
  243 | test.describe('Suscripciones', () => {
  244 | 
  245 |   /** Crea una suscripción vía API directa y retorna su chat_id. */
  246 |   async function crearSubPorApi(request) {
  247 |     const chatId = 'pw_' + Date.now();
  248 |     const resp = await request.post('/api/v1/suscripciones', {
  249 |       data: { chat_id: chatId, nombre: 'PW Test', regiones: ['Metropolitana', 'Valparaíso'] },
  250 |     });
  251 |     expect(resp.ok()).toBeTruthy();
  252 |     return chatId;
```