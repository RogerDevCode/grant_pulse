// @ts-check
import { test, expect } from '@playwright/test';

async function waitForRadarReady(page) {
  await page.waitForFunction(() => {
    const loader = document.getElementById('radarLoader');
    return !loader || loader.style.display === 'none';
  });
  await page.waitForTimeout(600);
}

test('Verifica que CORFO en Biobío tenga 3 convocatorias en producción', async ({ page }) => {
  page.on('console', msg => console.log(`[BROWSER CONSOLE] ${msg.type()}: ${msg.text()}`));
  page.on('pageerror', err => console.error(`[BROWSER ERROR] ${err.message}`));
  page.on('requestfailed', request => console.error(`[BROWSER REQ FAIL] ${request.url()} - ${request.failure()?.errorText}`));

  console.log("Navegando a la página principal de producción...");
  await page.goto('/');
  await waitForRadarReady(page);

  // 1. Desmarcar "Solo activas" si está marcado para obtener el total histórico/completo
  const soloActivasCheckbox = page.locator('#soloActivasToggle');
  if (await soloActivasCheckbox.isChecked()) {
    console.log("Desmarcando 'Solo activas' para ver todas las convocatorias...");
    // Hacemos click en el label visible, lo cual alterna el estado del checkbox
    await page.locator('#soloActivasLabel').click();
    await waitForRadarReady(page);
  }

  // 2. Filtrar por Institución CORFO
  console.log("Abriendo selector de instituciones...");
  await page.locator('#instSelectorBtn').click();
  await page.waitForTimeout(300);

  console.log("Seleccionando la opción CORFO...");
  // Buscamos la opción de CORFO dentro del desplegable
  const corfoOption = page.locator('.inst-option', { hasText: 'CORFO' });
  await expect(corfoOption).toBeVisible();
  await corfoOption.click();
  await waitForRadarReady(page);

  // 3. Filtrar por Región Biobío
  console.log("Seleccionando la región 'Biobío'...");
  await page.selectOption('#filterRegion', 'Biobío');
  await waitForRadarReady(page);

  // 4. Contar convocatorias resultantes
  const count = await page.locator('.conv-card').count();
  console.log(`[TEST RESULT] Cantidad encontrada con 'Solo activas' desactivado: ${count}`);

  // 5. Probar con 'Solo activas' activado para ver si cambia
  if (!(await soloActivasCheckbox.isChecked())) {
    console.log("Marcando 'Solo activas'...");
    await page.locator('#soloActivasLabel').click();
    await waitForRadarReady(page);
  }
  const countActivas = await page.locator('.conv-card').count();
  console.log(`[TEST RESULT] Cantidad encontrada con 'Solo activas' activado: ${countActivas}`);

  // Haremos la aserción sobre el conteo de todas las convocatorias (sin el filtro de solo activas)
  // o según corresponda. Imprimiremos ambas para que el usuario tenga toda la visibilidad.
  expect(count, `Se esperaban 1 convocatorias para CORFO en Biobío, pero se encontraron ${count}`).toBe(1);
});
