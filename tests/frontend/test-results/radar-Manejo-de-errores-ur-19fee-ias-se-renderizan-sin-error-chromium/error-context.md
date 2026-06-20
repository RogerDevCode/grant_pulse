# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: radar.spec.js >> Manejo de errores >> urls de convocatorias se renderizan sin error
- Location: radar.spec.js:386:3

# Error details

```
Error: expect(received).toBeGreaterThan(expected)

Expected: > 0
Received:   0
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
  291 |     await page.locator('#subChatId').fill(testChatId);
  292 |     await page.locator('#subBuscarBtn').click();
  293 |     await page.waitForTimeout(400);
  294 |     // Debe mostrar "Nueva" badge porque el chat_id no existe
  295 |     await expect(page.locator('#suscBadgeCreada')).toBeVisible();
  296 |     await page.locator('#subNombre').fill('Test Playwright');
  297 |     const checkboxes = page.locator('#subRegiones input[type="checkbox"]');
  298 |     await checkboxes.nth(0).check();
  299 |     await checkboxes.nth(1).check();
  300 |     await page.locator('#subGuardarBtn').click();
  301 |     await page.waitForTimeout(500);
  302 |     // Feedback de éxito
  303 |     await expect(page.locator('.susc-feedback--success')).toBeVisible();
  304 |     // Badge de activa aparece
  305 |     await expect(page.locator('#suscBadgeActiva')).toBeVisible();
  306 |   });
  307 | 
  308 |   test('error si se guarda sin regiones', async ({ page }) => {
  309 |     const testChatId = 'pw_' + Date.now();
  310 |     await page.goto('/');
  311 |     await page.waitForLoadState('networkidle');
  312 |     await page.locator('.nav-item[data-page="suscripciones"]').click();
  313 |     await page.waitForTimeout(300);
  314 |     await page.locator('#subChatId').fill(testChatId);
  315 |     await page.locator('#subBuscarBtn').click();
  316 |     await page.waitForTimeout(400);
  317 |     // No seleccionar regiones, solo guardar
  318 |     await page.locator('#subGuardarBtn').click();
  319 |     await page.waitForTimeout(300);
  320 |     await expect(page.locator('.susc-feedback--error')).toBeVisible();
  321 |   });
  322 | 
  323 |   test('toggle pausar/reactivar', async ({ page, request }) => {
  324 |     const chatId = await crearSubPorApi(request);
  325 |     await page.goto('/');
  326 |     await page.waitForLoadState('networkidle');
  327 |     await page.locator('.nav-item[data-page="suscripciones"]').click();
  328 |     await page.waitForTimeout(300);
  329 |     await page.locator('#subChatId').fill(chatId);
  330 |     await page.locator('#subBuscarBtn').click();
  331 |     await page.waitForTimeout(400);
  332 |     // Click en Pausar
  333 |     await page.locator('#subPausarBtn').click();
  334 |     await page.waitForTimeout(400);
  335 |     await expect(page.locator('#suscBadgePausada')).toBeVisible();
  336 |     await expect(page.locator('#subPausarLabel')).toHaveText('Reanudar');
  337 |     // Reactivar
  338 |     await page.locator('#subPausarBtn').click();
  339 |     await page.waitForTimeout(400);
  340 |     await expect(page.locator('#suscBadgeActiva')).toBeVisible();
  341 |   });
  342 | 
  343 |   test('eliminar suscripción con confirmación', async ({ page, request }) => {
  344 |     const chatId = await crearSubPorApi(request);
  345 |     await page.goto('/');
  346 |     await page.waitForLoadState('networkidle');
  347 |     await page.locator('.nav-item[data-page="suscripciones"]').click();
  348 |     await page.waitForTimeout(300);
  349 |     await page.locator('#subChatId').fill(chatId);
  350 |     await page.locator('#subBuscarBtn').click();
  351 |     await page.waitForTimeout(400);
  352 |     // Click Eliminar
  353 |     await page.locator('#subEliminarBtn').click();
  354 |     // Modal de confirmación
  355 |     await expect(page.locator('#confirmModal')).toHaveClass(/active/);
  356 |     // Confirmar
  357 |     await page.locator('#confirmModalOk').click();
  358 |     await page.waitForTimeout(500);
  359 |     // Vuelve al empty state
  360 |     await expect(page.locator('#suscEmpty')).toBeVisible();
  361 |   });
  362 | });
  363 | 
  364 | // ══════════════════════════════════════════════════════════════════════════
  365 | //  MANEJO DE ERRORES
  366 | // ══════════════════════════════════════════════════════════════════════════
  367 | 
  368 | test.describe('Manejo de errores', () => {
  369 |   test('carga inicial sin errores visibles', async ({ page }) => {
  370 |     await page.goto('/');
  371 |     await waitForRadarReady(page);
  372 |     // Verificar que no hay mensajes de error en la consola
  373 |     const errors = [];
  374 |     page.on('console', msg => {
  375 |       if (msg.type() === 'error') errors.push(msg.text());
  376 |     });
  377 |     await page.waitForTimeout(500);
  378 |     // El radar se cargó correctamente si hay cards o estado vacío
  379 |     const cards = page.locator('.conv-card');
  380 |     const empty = page.locator('#radarEmpty');
  381 |     const hasCards = (await cards.count()) > 0;
  382 |     const hasEmpty = await empty.isVisible();
  383 |     expect(hasCards || hasEmpty).toBe(true);
  384 |   });
  385 | 
  386 |   test('urls de convocatorias se renderizan sin error', async ({ page }) => {
  387 |     await page.goto('/');
  388 |     await waitForRadarReady(page);
  389 |     const cards = page.locator('.conv-card');
  390 |     const count = await cards.count();
> 391 |     expect(count).toBeGreaterThan(0);
      |                   ^ Error: expect(received).toBeGreaterThan(expected)
  392 |     // Click en la primera card para ver detalle
  393 |     await cards.first().click();
  394 |     await page.waitForTimeout(500);
  395 |     const body = page.locator('#detailModalBody');
  396 |     // No debe mostrar error
  397 |     await expect(body).not.toContainText(/Error al cargar/i);
  398 |   });
  399 | });
  400 | 
```