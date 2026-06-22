# Plan de Tests: Contabilización inconsistente de convocatorias

## Contexto del bug

Reportado por usuario: "corfo solo muestra 10 proyectos, cuando hay mas, la barra totalizadora no esta sincronizada con los proyectos de la tabla".

**Hallazgos del análisis de la API en producción** (https://grantpulse-production.up.railway.app):

| Endpoint | Valor | Observación |
|---|---|---|
| `/fuentes` (CORFO) | `total=67, abiertas=67` | Correcto a nivel BD |
| `/convocatorias?fuente_id=2&limit=24` | 24 items | Frontend pagina con page size 24 |
| `/convocatorias?fuente_id=2&limit=200` | 67 items | Total real |
| `/convocatorias/count?fuente_id=2&estado=ABIERTO` | `total=67` | Correcto |
| `/convocatorias/kpi?fuente_id=2&estado=ABIERTO` | `abiertas=67, instituciones=1, vencen_30=91, sin_fecha=24` | **Inconsistente**: `vencen_30=91` es global, no filtrado |
| `/convocatorias/kpi` (sin filtro) | `abiertas=350, instituciones=6, vencen_30=91, sin_fecha=256` | Global |

## Bugs identificados (B01-B05)

### B01: Paginación oculta el total real al usuario
**Severidad:** High
**Impacto:** El usuario ve 24 cards cuando hay 67. La pill dice "24 activas" pero realmente hay 67. Falso sentido de completitud.
**Causa raíz:** `PAGE_SIZE = 24` en `app.js` con paginación, sin opción "ver todos".
**Ubicación frontend:** `src/presentation/frontend/app.js:9` — `const PAGE_SIZE = 24;`

### B02: KPI "instituciones" se filtra incorrectamente
**Severidad:** High
**Impacto:** Al filtrar por CORFO, el KPI "instituciones" muestra 1, lo cual es lógicamente correcto si se filtra, pero contradictorio con la experiencia del usuario que espera ver cuántas fuentes tiene abiertas en general.
**Causa raíz:** En el endpoint `/kpi`, `instituciones` cuenta fuentes distintas en el subconjunto filtrado.
**Comportamiento esperado:** El KPI "instituciones" debería mostrar el total global de fuentes activas (6), o el frontend debería etiquetarlo como "instituciones en filtro".

### B03: KPI "vencen_30" mezcla filtrado y global
**Severidad:** Critical
**Impacto:** Con filtro CORFO activo, el KPI dice `vencen_30=91`, pero `91` es el total global (todas las fuentes), no las que vencen en 30 días dentro de CORFO. Datos engañosos para el usuario.
**Causa raíz:** En `src/presentation/api/routes.py` líneas 200-225, el cálculo de `vencen_30` no aplica el `base_filter` que sí se aplica a `abiertas`, `instituciones` y `sin_fecha`.
**Código problemático:**
```python
vencen_30_q = select(func.count(ConvocatoriaORM.id)).where(
    ConvocatoriaORM.estado == "ABIERTO",
    ConvocatoriaORM.fecha_cierre.isnot(None),
    ConvocatoriaORM.fecha_cierre >= now,
    ConvocatoriaORM.fecha_cierre <= now + timedelta(days=30),
)
# Falta: .where(base_filter) cuando hay filtros activos
```

### B04: KPI "sin_fecha" sin contexto del filtro
**Severidad:** Medium
**Impacto:** El usuario espera coherencia entre `abiertas` (que sí se filtra) y `sin_fecha` (que también se filtra en realidad, pero `256` global vs `24` filtrado genera dudas).
**Verificación:** `sin_fecha=24` con filtro CORFO es correcto (24 de las 67 de CORFO no tienen fecha). Pero el usuario no sabe que el filtro está aplicado.

### B05: Pill "24 activas" no es descriptivo
**Severidad:** Medium
**Impacto:** La pill muestra un número sin contexto. "24 activas" podría significar "24 activas en esta página" o "24 activas en total". El usuario no puede distinguir.
**Causa raíz:** `updateActivePill()` usa solo `state.convTotal` que es el conteo de la página actual si no se ha cargado, o el total real si se cargó via `countData.total`. Inconsistencia entre `loadRadar()` y `renderConvGrid()`.

## Tests E2E a generar

Los tests usan Playwright contra `https://grantpulse-production.up.railway.app/` con perfil limpio (sin extensiones), modo headless, y verificación cruzada con la API.

### TC-RADAR-001: Conteo total de cards coincide con el endpoint /count
**Prioridad:** P0
**Pasos:**
1. Navegar a https://grantpulse-production.up.railway.app/
2. Esperar a que el radar cargue
3. Leer el texto de `#resultNum` (pill de resultados)
4. Leer el texto de `#activePillLabel`
5. Contar cards `.conv-card` visibles en el DOM
6. Hacer GET a `/api/v1/convocatorias/count?estado=ABIERTO` y comparar

**Esperado:**
- `#resultNum` debe ser **igual** al `total` de `/count`
- `total` debe ser **igual** al conteo de todas las cards (sumando páginas si es necesario)
- `#activePillLabel` debe decir "N activas" donde N = total

**Falla esperada (bug B01):** `#resultNum` mostrará 24 (página actual) en lugar de 350 (total global).

### TC-RADAR-002: Totalización coherente al filtrar por CORFO
**Prioridad:** P0
**Pasos:**
1. Navegar a /
2. Abrir dropdown de instituciones, seleccionar "CORFO"
3. Esperar a que el radar recargue
4. Leer `#resultNum`
5. Contar cards en la primera página
6. Contar total de cards navegando todas las páginas (botón "Siguiente")
7. GET `/convocatorias/count?estado=ABIERTO&fuente_id=2` y comparar

**Esperado:**
- Suma de todas las cards en todas las páginas = total del endpoint
- `#resultNum` debe mostrar el total acumulado, no solo la página actual

**Falla esperada (bug B01):** CORFO tiene 67 items; el usuario solo ve "24 activas" en la primera página. La pill no comunica el total real.

### TC-RADAR-003: KPI "abiertas" coincide con el conteo real
**Prioridad:** P1
**Pasos:**
1. Navegar a /
2. Leer `#kpiAbiertas`
3. GET `/convocatorias/kpi?estado=ABIERTO` y leer campo `abiertas`
4. Comparar

**Esperado:** Ambos números deben ser idénticos.

### TC-KPI-004: KPI "vencen_30" coherente con filtro aplicado
**Prioridad:** P0
**Pasos:**
1. Navegar a /
2. Sin filtro: leer `#kpiVencen30`
3. Seleccionar CORFO en dropdown
4. Esperar recarga
5. Leer `#kpiVencen30` con filtro
6. GET `/convocatorias/kpi?fuente_id=2&estado=ABIERTO` y leer `vencen_30`
7. Verificar: el número con filtro debe ser ≤ al número sin filtro

**Esperado:** Si CORFO tiene X que vencen en 30 días, el KPI filtrado debe ser X (no el global 91).

**Falla esperada (bug B03):** El KPI con filtro seguirá mostrando 91 (valor global) porque el endpoint no aplica el filtro a `vencen_30`.

### TC-KPI-005: KPI "instituciones" se mantiene o etiqueta al filtrar
**Prioridad:** P1
**Pasos:**
1. Navegar a /
2. Sin filtro: leer `#kpiInstituciones` (debería ser 6)
3. Seleccionar CORFO
4. Leer `#kpiInstituciones` con filtro
5. Verificar: si muestra 1, debe haber una etiqueta que diga "en filtro" o similar

**Esperado:** El KPI no debería cambiar drásticamente de 6 a 1 sin indicación visual, o debería etiquetarse como "fuentes en filtro".

**Falla esperada (bug B02):** El KPI baja de 6 a 1 sin contexto, dejando al usuario confundido.

### TC-PAGINACION-006: La paginación muestra correctamente el total
**Prioridad:** P1
**Pasos:**
1. Navegar a /
2. Contar botones de paginación en `#convPagination`
3. Multiplicar `PAGE_SIZE` (24) por número de páginas - 1
4. Comparar con el total del endpoint
5. Hacer clic en "Siguiente" varias veces
6. Sumar todas las cards vistas
7. Verificar suma = total API

**Esperado:** La suma de cards en todas las páginas debe coincidir con el total del endpoint.

### TC-PILL-007: Pill de resultados refleja el total, no la página
**Prioridad:** P0
**Pasos:**
1. Navegar a /
2. Si la primera página tiene 24 cards, pero el total es 67 (CORFO), la pill debe decir "67 activas", no "24 activas"
3. Comparar `#activePillLabel` con `countData.total` del endpoint

**Esperado:** La pill debe decir el total real. El "24" es engañoso.

**Falla esperada (bug B05):** `#activePillLabel` muestra solo el conteo de la página actual, no el total.

### TC-INSTITUCIONES-008: Página de Instituciones muestra total correcto
**Prioridad:** P1
**Pasos:**
1. Navegar a / y luego a Instituciones
2. Para cada card `.inst-card`, leer "Activas" y "Total"
4. Sumar todos los "Activas" y comparar con KPI `#kpiAbiertas`
5. Sumar todos los "Total" y comparar con `#convocatorias/count`

**Esperado:** Suma de activas en Instituciones = KPI abiertas global. Suma de totales = total de la API.

**Falla esperada:** Las instituciones que devuelven `total_convocatorias=0` (ej: ANID inactiva) rompen la suma si se hace por institución individual.

### TC-NAV-009: Badge del sidebar "Radar" refleja el total global
**Prioridad:** P2
**Pasos:**
1. Navegar a /
2. Leer `#navBadgeRadar` (badge en el sidebar)
3. GET `/convocatorias/count?estado=ABIERTO`
4. Comparar

**Esperado:** El badge debe mostrar el número total o estar vacío.

## Mapeo bug → test

| Bug | Test que lo detecta |
|---|---|
| B01 - Paginación oculta total | TC-RADAR-001, TC-RADAR-002, TC-PAGINACION-006 |
| B02 - KPI instituciones filtrado | TC-KPI-005, TC-INSTITUCIONES-008 |
| B03 - KPI vencen_30 global | TC-KPI-004 |
| B04 - Sin_fecha sin contexto | TC-INSTITUCIONES-008 |
| B05 - Pill "24 activas" engañoso | TC-PILL-007, TC-RADAR-001 |

## Estructura de los tests

Ubicación: `tests/frontend/contabilidad.spec.js` (nuevo archivo)

Cada test:
- Perfil limpio: `browser.new_context()` por test
- Modo headless: `chromium.launch({ headless: true })`
- Sin extensiones: `args: ['--disable-extensions']`
- Cleanup: al final, restaurar el filtro a "Todas"

Verificación cruzada:
- Tests hacen GET a `/api/v1/convocatorias/count?*` y `/api/v1/convocatorias/kpi?*` desde el test
- Comparan contra valores leídos del DOM

## Riesgos del plan

- **Red flaky:** Los tests contra producción pueden fallar por latencia. Mitigación: `retries: 1`, timeouts generosos.
- **Datos cambiantes:** El conteo de CORFO puede cambiar entre requests. Mitigación: tolerancia de ±5%.
- **Dependencias entre tests:** Mitigación: cada test usa `browser.new_context()` y navega desde cero.

## Entregables

1. `tests/frontend/contabilidad.spec.js` — 9 tests E2E
2. `tests/frontend/reports/contabilidad-bugs.md` — reporte de bugs B01-B05 con evidencia
3. `tests/frontend/fixtures/contabilidad-helpers.js` — funciones helper para verificación cruzada con API
