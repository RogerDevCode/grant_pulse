# Plan: Estado `PERMANENTE` para convocatorias sin fecha de cierre

## Contexto

**256 de 350** convocatorias activas (73%) no tienen fecha de cierre. Análisis de muestra:
- `FNDR 8% Región de O'Higgins - Deportistas Destacados`
- `Fondo de la Música: Concurso de Composición Musical`
- `Sello de Excelencia a la Artesanía Chile 2026`
- `Fondo Concursable SERNAC - SEGUNDO LLAMADO 2026`

Todas son **fondos concursables permanentes**: no cierran, reciben postulaciones hasta agotar cupo. El usuario no tiene forma de distinguirlas de las que sí cierran.

## Decisión de diseño

Agregar un **cuarto estado canónico** `PERMANENTE` a la entidad `Convocatoria.estado`. Se asigna automáticamente durante la normalización cuando:
- `estado crudo` no se reconoce (cae en `DESCONOCIDO`)
- Y la convocatoria no tiene `fecha_cierre`

Las convocatorias con estado `DESCONOCIDO` + `fecha_cierre` futura siguen siendo `ABIERTO` (comportamiento actual preservado).

## Cambios concretos

### 1. `src/core/domain/entities.py` — agregar `PERMANENTE` al catálogo implícito

El estado es un `str` libre en la entidad, no hay enum. Solo agrego el valor como string en la docstring de `Convocatoria.estado` para documentación.

```python
estado: str  # Valores canónicos: "ABIERTO", "CERRADO", "PROXIMAMENTE", "FINALIZADO", "PERMANENTE"
```

### 2. `src/core/application/normalizer.py` — lógica de asignación

Modificar el bloque existente que promueve `DESCONOCIDO + fecha_cierre futura → ABIERTO`:

```python
# Antes:
if estado == "DESCONOCIDO" and fecha_cierre_val is not None and fecha_cierre_val >= now:
    estado = "ABIERTO"

# Después:
if estado == "DESCONOCIDO" and fecha_cierre_val is not None and fecha_cierre_val >= now:
    estado = "ABIERTO"
elif estado == "DESCONOCIDO" and fecha_cierre_val is None:
    # Fondo concursable permanente: sin fecha de cierre
    estado = "PERMANENTE"
```

### 3. `src/core/domain/estado_normalizer.py` — clases CSS

Agregar `PERMANENTE` al mapa de estilos para que el badge tenga color propio:

```python
ESTADO_BADGES = {
    "ABIERTO": "badge-green",
    "PERMANENTE": "badge-cyan",     # nuevo — fondo concursable abierto todo el año
    "PROXIMAMENTE": "badge-amber",
    "CERRADO": "badge-red",
    "FINALIZADO": "badge-red",
    "SUSPENDIDO": "badge-red",
    "ADJUDICADO": "badge-red",
    "DESCONOCIDO": "badge-gray",
}
```

### 4. `src/presentation/api/routes.py` — nuevo endpoint de filtro

Agregar parámetro `estado` opcional al endpoint `/convocatorias/count` (ya existe) y `/convocatorias/kpi`. La query ya acepta `estado`, solo necesito actualizar el KPI:

```python
# En get_convocatorias_kpi, agregar conteo por estado:
return {
    "abiertas": abiertas,
    "permanentes": permanentes,  # nuevo
    "vencen_30": vencen_30_count,
    "instituciones": instituciones,
    "sin_fecha": sin_fecha,
}
```

Query para `permanentes`:
```python
permanentes_q = select(func.count(ConvocatoriaORM.id)).where(
    ConvocatoriaORM.estado == "PERMANENTE"
)
if base_filter is not True:
    permanentes_q = permanentes_q.where(base_filter)
permanentes = (await session.execute(permanentes_q)).scalar() or 0
```

### 5. `src/presentation/frontend/index.html` — filtro adicional

Agregar en la toolbar de filtros, después del toggle "Solo activas":

```html
<label class="solo-permanentes-toggle" id="soloPermanentesLabel"
       title="Cuando está activo, incluye convocatorias con estado PERMANENTE (fondos concursables sin fecha de cierre). Por defecto se excluyen para enfocarse en convocatorias con fecha límite.">
  <input type="checkbox" id="soloPermanentesToggle">
  <span class="toggle-switch"></span>
  <span class="toggle-text">Incluir permanentes</span>
</label>
```

### 6. `src/presentation/frontend/app.js` — estado del frontend

Agregar a `state`:
```javascript
const state = {
  // ... existente
  incluirPermanentes: false,
};
```

Pasar el parámetro en las llamadas a la API:
```javascript
// En loadRadar():
if (state.incluirPermanentes) {
  listParams.set('estado', 'ABIERTO,PERMANENTE');  // o usar listaParams separados
  filterParams.set('estado', 'ABIERTO,PERMANENTE');
}
```

Mejor: agregar nuevo parámetro `incluir_permanentes=true` al endpoint, evitar lógica compleja en frontend.

**Mejor opción**: el frontend ya envía `estado=ABIERTO` cuando "Solo activas" está activo. Cambiar a:
```javascript
const estadoFilter = state.incluirPermanentes ? 'ABIERTO' : 'ABIERTO';
// (PERMANENTE siempre se incluye cuando no hay filtro de estado,
//  o se filtra explícitamente)
```

Pendiente: refinar en la implementación. El criterio simple es:
- `Solo activas` ON (default) → mostrar solo `ABIERTO` (excluye permanentes)
- `Solo activas` ON + `Incluir permanentes` ON → mostrar `ABIERTO` + `PERMANENTE`
- `Solo activas` OFF → mostrar todo

### 7. `src/presentation/frontend/app.js` — render del badge

En `badgeClass()` agregar el caso `PERMANENTE`:

```javascript
function badgeClass(estado) {
  const e = (estado || '').toUpperCase();
  if (e.includes('PERMANENTE'))    return 'badge-cyan';
  // ... resto igual
}
```

### 8. `src/presentation/frontend/index.html` — KPI "sin fecha"

Actualizar el tooltip de `kpiSinFecha` para explicar la conexión con permanentes:
```html
<div class="kpi-item kpi-purple" title="Convocatorias activas sin fecha de cierre registrada. La mayoría son fondos concursables permanentes (estado PERMANENTE). Active el toggle 'Incluir permanentes' para verlas.">
```

### 9. Migración de datos existentes

Script `scripts/migrations/migrate_to_permanente.py` (nuevo, opcional):

```python
"""
Migración: marcar como PERMANENTE las convocatorias activas sin fecha de cierre.
Idempotente. Ejecutar una vez.
"""
import asyncio
from sqlalchemy import update
from src.infra.db.connection import AsyncSessionLocal
from src.infra.db.models import ConvocatoriaORM

async def migrate():
    async with AsyncSessionLocal() as session:
        stmt = (
            update(ConvocatoriaORM)
            .where(
                ConvocatoriaORM.estado == "ABIERTO",
                ConvocatoriaORM.fecha_cierre.is_(None),
            )
            .values(estado="PERMANENTE")
        )
        result = await session.execute(stmt)
        await session.commit()
        print(f"Migradas {result.rowcount} convocatorias a PERMANENTE")

if __name__ == "__main__":
    asyncio.run(migrate())
```

**No requiere Alembic** — agregar un valor a un campo `str` no cambia el schema de la tabla.

### 10. `tests/unit/test_estado_permanente.py` — tests nuevos

- `test_convocatoria_sin_fecha_promueve_a_permanente`: input sin fecha_cierre, estado final `PERMANENTE`
- `test_convocatoria_con_fecha_promueve_a_abierto`: input con fecha futura, estado final `ABIERTO`
- `test_convocatoria_con_fecha_pasada_se_descarta`: filtro existente preserva comportamiento
- `test_kpi_incluye_permanentes`: el endpoint `/kpi` retorna el campo `permanentes`
- `test_badge_permanente_retorna_cyan`: `badgeClass("PERMANENTE")` retorna `"badge-cyan"`

## Archivos a modificar

| Archivo | Tipo de cambio |
|---|---|
| `src/core/application/normalizer.py` | Lógica de promoción a `PERMANENTE` |
| `src/core/domain/estado_normalizer.py` | Mapa de badges con `PERMANENTE` |
| `src/core/domain/entities.py` | Docstring de `estado` |
| `src/presentation/api/routes.py` | KPI `permanentes` |
| `src/presentation/frontend/index.html` | Toggle "Incluir permanentes" + tooltip KPI |
| `src/presentation/frontend/app.js` | Estado, badge, filtro, paso de parámetro |
| `scripts/migrations/migrate_to_permanente.py` | Nuevo (idempotente) |
| `tests/unit/test_estado_permanente.py` | 5 tests nuevos |

## Compatibilidad hacia atrás

- Backend acepta `estado=ABIERTO` (filtro actual). El nuevo `PERMANENTE` es aditivo.
- Frontend: si el backend retorna `estado="PERMANENTE"` y el frontend no lo conoce, lo trata como `DESCONOCIDO` con badge gris. **Por eso la primera migración es al backend (paso 1-4)**, luego frontend.
- Datos existentes: no se ven afectados hasta que se ejecute la migración (paso 9).

## Plan de ejecución

1. **Backend primero**: normalizer, estado_normalizer, routes.py → tests → commit
2. **Migración**: ejecutar script en Railway para marcar 256 items como PERMANENTE
3. **Frontend**: app.js, index.html → tests visuales → commit
4. **Verificación**: deploy en Railway, verificar que (a) los badges se ven cyan, (b) el toggle filtra correctamente, (c) los KPIs incluyen `permanentes`

## Riesgos y mitigaciones

- **Riesgo**: cambiar `estado` de registros existentes rompe suscripciones o alertas ya enviadas. **Mitigación**: las suscripciones filtran por región, no por estado, así que no se afectan. Las alertas ya enviadas son inmutables.
- **Riesgo**: el toggle "Incluir permanentes" confunde a usuarios que esperan ver solo lo urgente. **Mitigación**: por defecto está OFF; tooltip explica que las permanentes son fondos abiertos todo el año.
- **Riesgo**: la BD local de test no tiene la migración aplicada. **Mitigación**: el script de migración es idempotente y se puede correr antes de los tests.
- **Riesgo**: el `badge-cyan` no existe en CSS. **Mitigación**: verificar que el token CSS `--cyan` existe en `style.css`; si no, agregarlo.

## Entregables finales

1. Backend: cambios en normalizer, estado_normalizer, routes.py
2. Frontend: tooltip mejorado, toggle nuevo, badge cyan
3. Script de migración idempotente
4. Tests unitarios (5 nuevos)
5. Documentación: actualizar `AGENTS.md` sección 2 si aplica
