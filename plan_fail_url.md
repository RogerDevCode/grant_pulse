# Plan Técnico: Política de URLs Inválidas/Rotas en Convocatorias

## Estado Actual (Resumen)

| Capa | Comportamiento Actual | Gap vs. Tu Criterio |
|------|----------------------|---------------------|
| **Normalizer** | `_is_valid_url()` hace HEAD/GET en extracción; si falla → `url_final=None` y fuerza `estado=CERRADO` si no hay indicios offline | Hace requests de red en normalización (no corresponde); no descarta items con URL sintácticamente inválida |
| **Repositorio** | Guarda `url_detalle` como nullable; sin validación al persistir | Falta fail-fast en creación de datos nuevos inválidos |
| **Change Detector** | Compara `url_detalle` como campo más; no trackea 404s consecutivos | No detecta "URL se volvió 404 consistentemente" |
| **Maintenance** | `clean_expired_convocatorias()` borra por `fecha_cierre` + estado no vigente; `run_clean_db()` borra >6 meses + estado≠ABIERTO | Falta política explícita por URL 404 confirmada |
| **API/Dashboard** | Filtra por `estado` (ABIERTO/CERRADO) | Sin filtro explícito "vigente = operable" |

---

## Plan de Implementación (4 Bloques Validables)

### Bloque 1: Fail-fast en Normalización (`src/core/application/normalizer.py`)
**Objetivo**: Descartar items con URL sintácticamente inválida *antes* de crear `Convocatoria`.

**Cambios**:
1. **Eliminar requests HTTP en `_is_valid_url()`** — la validación sintáctica basta en extracción. El check de red pertenece a monitoreo.
2. **Validar normalización contra `url_base`**: si `url_detalle` es relativa y no resuelve contra `url_base` → descartar.
3. **Log estructurado** con `fuente_id`, `run_id`, `identificador_externo`, `motivo="URL_INVALIDA"`.
4. **Nueva excepción**: `NormalizationError` con código `URL_INVALIDA` (ya existe la jerarquía).

**Archivos**: `normalizer.py` (líneas 26-75, 430-438)

---

### Bloque 2: Detección de URL 404/410 Confirmada en Monitoreo
**Objetivo**: Trackear fallos de URL consecutivos y generar evento `NO_VIGENTE` tras N confirmaciones.

**Cambios**:
1. **Nuevo campo en `ConvocatoriaORM`**: `url_check_failures: int = 0` (contador de 404/410 consecutivos) y `ultimo_check_url: datetime | None`.
2. **Estado final**: `"CERRADO"` (reusado, no nuevo estado, con metadata opcional para distinguir motivo).
3. **Servicio de verificación de URLs** (`src/core/domain/url_checker.py`):
   - Ejecutar HEAD/GET *solo* en monitoreo (no en normalización)
   - Clasificar: `VALID`, `TRANSIENT_ERROR` (5xx, timeout, 403, network), `PERMANENT_GONE` (404, 410)
   - Polite: timeout=3s, retries=1, follow_redirects=True
4. **En `MonitoreoUseCase`** (tras detectar cambios):
   - Para cada convocatoria *existente* de la fuente (no solo las nuevas): verificar URL
   - Si `PERMANENT_GONE`: incrementar contador; si ≥ `UMBRAL_CONFIRMACION` (3) → generar `EventoCambio(tipo="MODIFICACION", es_relevante=True)` con delta en `estado` a `"CERRADO"`, set `metadatos.url_check_failed=true`
   - Si `VALID` o `TRANSIENT_ERROR`: resetear contador a 0
   - Reset contador también si la convocatoria es *nueva* en esta corrida (no penalizar por falta de historial)
5. **Log estructurado** con `fuente_id`, `run_id`, `convocatoria_id`, `url_check_result`, `failure_count`.

**Archivos nuevos/modificados**:
- `src/infra/db/models.py` (+2 campos en `ConvocatoriaORM`)
- `alembic/versions/..._add_url_check_fields.py` (migración)
- `src/core/domain/url_checker.py` (nuevo)
- `src/core/application/use_cases.py` (integración en `MonitoreoUseCase`)
- `src/core/domain/services.py` (para crear el delta de estado)

---

### Bloque 3: Maintenance — Limpieza por URL Confirmada
**Objetivo**: Hard-delete solo tras ventana de gracia, no al primer fallo.

**Cambios en `src/infra/maintenance.py`**:
1. **Nueva función `clean_unavailable_convocatorias(dias_gracia: int = 30)`**:
   - Borra convocatorias con `metadatos.url_check_failed=true` Y `ultimo_check_url < ahora - dias_gracia`
   - Elimina historial asociado (FK)
2. **Integrar en CLI** como subcomando de `clean-db` o comando separado `clean-unavailable`.
3. **Ejecutar automáticamente** en el worker tras cada ciclo (después de `clean_expired_convocatorias`).

**Archivos**: `maintenance.py`, `cli.py`

---

### Bloque 4: API/Dashboard — Filtro "Vigentes Operativamente"
**Objetivo**: Que el frontend muestre solo convocatorias accionables.

**Cambios en `src/presentation/api/routes.py`**:
1. **Nuevo query param** `vigente: bool` en `/convocatorias` y `/convocatorias/filtradas`
2. **Lógica**: `vigente=True` → `estado NOT IN ("CERRADO", "ADJUDICADO", "SUSPENDIDO", "FINALIZADO") AND (metadatos.url_check_failed IS NULL OR metadatos.url_check_failed = false)`
3. **Actualizar KPIs** (`/convocatorias/kpi`) para excluir convocatorias con `metadatos.url_check_failed=true`.

**Archivos**: `routes.py`

---

## Dependencias y Orden

```
Bloque 1 (Normalización)     → Independiente, base
       ↓
Bloque 2 (Monitoreo + URL Check) → Requiere migración BD (Bloque 2.1)
       ↓
Bloque 3 (Maintenance)         → Usa campos del Bloque 2
       ↓
Bloque 4 (API)                 → Usa estados del Bloque 2
```

---

## Validaciones Post-Cambio (por bloque)

| Bloque | Validación |
|--------|------------|
| 1 | `pytest tests/unit/test_normalizer.py` — items con URL inválida se descartan, log estructurado presente |
| 2 | Test de integración: convocatoria existente → 404 en run 1 (contador=1, estado intacto) → 404 en run 2 (contador=2) → 404 en run 3 (evento MODIFICACION, estado=CERRADO, metadatos.url_check_failed=true); 500 no incrementa contador; convocatorias nuevas no penalizadas |
| 3 | `pytest tests/unit/test_maintenance.py` — `clean_unavailable_convocatorias` borra solo tras ventana; prueba end-to-end con monitoreo → limpieza |
| 4 | `pytest tests/unit/test_api.py` — filtro `vigente=true` excluye `url_check_failed=true` |

---

## Respuestas a Preguntas de Diseño

1. **Umbral de confirmación**: `3` corridas consecutivas 404/410 (ajustado de 2 a 3 para reducir falsos positivos)
2. **Estado final**: `"CERRADO"` reusado, con `metadatos.url_check_failed=true` para distinguir motivo
3. **Verificación de URL en monitoreo**: todas las convocatorias existentes de la fuente cada corrida (para detectar desapariciones silenciosas)
4. **Ventana de gracia para hard-delete**: `30` días tras marcar `url_check_failed=true`
5. **Campo `url_check_failures`**: `INTEGER` (acepta valores pequeños, margen de seguridad)

---

## Notas de Implementación

### Seguridad y Performance
- El URL checker usa semáforo de concurrencia (máx 5 checks simultáneos) para evitar sobrecargar fuentes
- Timeout corto (3s) con una sola reintento
- Se siguen redirecciones (máx 5) para detectar 404 final
- User-Agent estándar para evitar bloqueos por bot

### Manejo de Errores
- Errores de red/timeout → `TRANSIENT_ERROR` → reset contador (no penalizar por problemas temporales)
- 403/405 → `TRANSIENT_ERROR` (podría ser WAF/rate limit)
- 404/410 → `PERMANENT_GONE` → incrementar contador
- Cualquier 2xx/3xx que termine en 2xx → `VALID` → reset contador

### Compatibilidad hacia atrás
- Los campos nuevos son nullable con default 0/NULL
- Las migraciones son ADD COLUMN, no destructive
- El lógica de normalización es más estricta (mejor), pero solo afecta a *nuevas* extracciones
- Las convocatorias existentes siguen funcionando; el monitoreo las irá marcando progresivamente

### Observabilidad
- Logs estructurados en normalización (descartes) y monitoreo (checks de URL)
- Métricas potenciales: `url_check_total`, `url_check_failures_transient`, `url_check_failures_permanent`, `convocatorias_marcadas_no_disponibles`