# Plan de Revisión y Corrección QA — GrantPulse (qa-rev-plus.md)

Este plan de revisión estructurado sigue la hoja de ruta y fases definidas en `qa-rev-plus.md`.

---

## 1. MAPA DE CONTEXTO (Fase 0)

### Árbol de módulos clave
- [src/core/domain/entities.py](file:///home/manager/Sync/python_proyects/grant_pulse/src/core/domain/entities.py): Entidades del dominio (`Fuente`, `Convocatoria`, `Delta`, etc.) validadas con Pydantic.
- [src/core/domain/exceptions.py](file:///home/manager/Sync/python_proyects/grant_pulse/src/core/domain/exceptions.py): Jerarquía canónica de excepciones.
- [src/core/application/normalizer.py](file:///home/manager/Sync/python_proyects/grant_pulse/src/core/application/normalizer.py): Procesamiento, regex, normalización de montos, fechas y estados.
- [src/infra/db/models.py](file:///home/manager/Sync/python_proyects/grant_pulse/src/infra/db/models.py): Esquemas ORM de SQLAlchemy mapeados a tablas de PostgreSQL.
- [src/infra/db/repository.py](file:///home/manager/Sync/python_proyects/grant_pulse/src/infra/db/repository.py): Persistencia concreta de entidades.
- [src/infra/sources/catalog.py](file:///home/manager/Sync/python_proyects/grant_pulse/src/infra/sources/catalog.py): Catálogo de fuentes en código alineado con YAMLs.
- [src/infra/scraping/](file:///home/manager/Sync/python_proyects/grant_pulse/src/infra/scraping): Implementaciones de scrapers (estático, APIs, Playwright, LLM).
- [src/presentation/api/main.py](file:///home/manager/Sync/python_proyects/grant_pulse/src/presentation/api/main.py): Punto de entrada y configuraciones de la API web.

### Dependencias externas reales vs declaradas
Todas las dependencias principales están declaradas en [pyproject.toml](file:///home/manager/Sync/python_proyects/grant_pulse/pyproject.toml). Se observa:
- Opcionales/Grupos de desarrollo bien segmentados.
- Se cuenta con `jellyfish` y `markdownify` en runtime opcional mediante guards `try/except ModuleNotFoundError`, pero mypy falla al tiparlos si se les asigna `None`.

### Discrepancias detectadas
- **Drift/Atributo Inexistente en Tests**: Los tests unitarios en `test_api.py` y `test_healthcheck.py` intentan mockear `_ensure_startup_schema` en `src.presentation.api.main`, pero dicha función no existe en la implementación de la API. Esto hace que fallen de forma inmediata.
- **Incompatibilidades de Tipado en Normalizador**: En `src/core/application/normalizer.py:493`, `limite_cierre` es una variable que puede ser `None` según la inferencia de tipo, lo cual genera un error de tipado al compararse con `now` (`limite_cierre < now`).

### TODOs y placeholders encontrados
- Uso de `aiosmtplib = None` y `jellyfish = None` que causan errores en mypy si no se usan anotaciones o ignores específicos.

---

## 2. INFORME DE ERRORES ESTÁTICOS (Fase 1)

| Archivo | Línea | Código/Tipo de Error | Severidad | Causa Raíz | Corrección Propuesta |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `src/core/domain/services.py` | 11 | assignment / type mismatch | ADVERTENCIA | Asignación de `None` a la variable de módulo importado `jellyfish`. | Agregar `# type: ignore[assignment]` o usar un boolean flag para la presencia del módulo. |
| `src/infra/notifications/email_adapter.py` | 10 | assignment / type mismatch | ADVERTENCIA | Asignación de `None` a la variable de módulo importado `aiosmtplib`. | Agregar `# type: ignore[assignment]`. |
| `src/infra/llm/client.py` | 26 | assignment / Cannot assign to a type | ADVERTENCIA | Asignación de `None` a `_HTMLParser` (alias de clase). | Agregar `# type: ignore[assignment, misc]`. |
| `src/infra/llm/client.py` | 38 | assignment / type mismatch | ADVERTENCIA | Asignación de `None` a `_markdownify_impl` (función importada). | Agregar `# type: ignore[assignment]`. |
| `src/core/application/normalizer.py` | 493 | Unsupported operand types (`datetime` and `None`) | BLOQUEANTE | `limite_cierre` puede ser `None` y se usa en comparación `limite_cierre < now`. | Cambiar la condición a `if limite_cierre and limite_cierre < now:`. |
| `src/infra/maintenance.py` | 5, 8, 10, 12 | Unused imports (Ruff F401) | INFORMATIVO | Imports no utilizados (`HttpUrl`, `_infer_region_with_llm`, `Fuente`, etc.). | Limpiar imports innecesarios en `src/infra/maintenance.py`. |

---

## 3. INFORME DE LÓGICA Y CONTRATOS (Fase 2)

1. **Test Mock Drift (API vs Tests)**:
   - *Impacto*: Falla inmediata al correr las pruebas de la API/Healthcheck en entornos locales y CI.
   - *Solución*: Eliminar los mocks de `_ensure_startup_schema` en `test_api.py` y `test_healthcheck.py` ya que esa función ha sido removida/reemplazada en el flujo de inicialización asíncrono en background.
2. **Detección de Cambios de Fecha y Zonas Horarias**:
   - *Impacto*: Comparaciones incorrectas o falsas alertas de cambio de fecha si una fecha es naive y otra aware.
   - *Solución*: Garantizar que toda comparación en `ChangeDetectorService` fuerce timezone UTC o mantenga uniformidad.
3. **Manejo de Respuestas Vacías en Scrapers Estáticos**:
   - *Impacto*: Si el selector CSS existe pero está vacío o mal estructurado en la web de origen, se puede guardar basura.
   - *Solución*: Añadir validación estricta y fallar temprano (`ExtractionError`) si campos críticos requeridos son cadenas vacías no reconocidas.

---

## 4. INFORME DE COBERTURA Y CÓDIGO MUERTO (Fase 3)

### Porcentajes de cobertura por módulo clave
- `src/core/application/enricher.py`: **0%**
- `src/core/application/normalizer.py`: **63%**
- `src/infra/cli.py`: **24%**
- `src/infra/db/repository.py`: **33%**
- `src/infra/llm/client.py`: **53%**
- `src/infra/notifications/email_adapter.py`: **21%**
- `src/infra/notifications/telegram_adapter.py`: **33%**
- `src/presentation/api/routes.py`: **13%**

### Código Muerto detectado
- Métodos del repositorio en `src/infra/db/repository.py` que no son consumidos por ningún caso de uso activo de la aplicación o API.
- Imports no utilizados identificados por Ruff en `src/infra/maintenance.py`.

---

## 5. INFORME RED TEAM (Fase 4)

| Vector de Ataque | Impacto | ¿Detectado hoy? | Corrección |
| :--- | :--- | :--- | :--- |
| **Prompt Injection vía HTML** | El LLM altera su output o extrae datos incorrectos guiado por instrucciones maliciosas inyectadas en campos de texto de la web scrapeada. | NO | Sanitizar/limpiar el texto extraído y usar instrucciones de sistema ultra-restrictivas y delimitadores claros de datos (e.g. triple comilla o tags XML) para aislar la entrada. |
| **Race Conditions en Scheduler** | Doble ejecución simultánea de los scrapers produciendo alertas duplicadas o drifts de estado en Base de Datos. | NO | Implementar un mecanismo de bloqueo (Lock distribuido usando `SELECT FOR UPDATE` o similar en BD) al inicio del proceso de sincronización/run. |
| **SQL Injection Dinámico** | Ejecución de comandos arbitrarios en Postgres si se concatenan queries sin ORM. | SÍ (protegido por uso de SQLAlchemy) | Asegurar que todas las consultas utilicen parámetros bindeados del ORM y no construcciones de strings dinámicos de SQL raw. |

---

### Opción Recomendada: **Opción D — Validación semántica de dominio** combinada con **Opción A (Cross-validation)**
- *Justificación*: El sistema corre 1-2 veces al día sobre unas 20-50 fuentes. La opción D provee la mejor relación costo/beneficio porque evita alertas absurdas (como montos fuera de rango o fechas de cierre anteriores a la fecha de apertura) sin requerir llamadas adicionales a red o LLMs.
- *Contrato Propuesto*:
  ```python
  class DomainValidator:
      def validate(self, convocatoria: Convocatoria) -> ValidationResult:
          # Valida rangos de montos, coherencia de fechas y consistencia de región.
  ```

### Estrategia de Mitigación y Normalización para Rangos de Montos
Para evitar la confusión y pérdida de datos en convocatorias que definen un rango (ej: *"desde $3.000.000 hasta $75.000.000"* o *"mínimo 5M, máximo 20M"*), y **prescindiendo del uso de expresiones regulares complejas** (las cuales requieren pruebas combinatorias costosas para garantizar cobertura al 100% y tienden a fallar ante variaciones de formato), implementamos un enfoque algorítmico puro:

1. **Extracción Algorítmica de Números (Libre de Regex)**:
   - Procesar secuencialmente los caracteres del texto.
   - Agrupar caracteres numéricos consecutivos permitiendo puntos y comas como separadores (ej: `.` y `,`), ignorando símbolos no numéricos (`$`, espacios, letras).
   - Dividir por palabras o "tokens" y limpiar caracteres no deseados en los extremos para identificar candidatos numéricos válidos.
2. **Criterio de Selección de Techo Financiero (Monto Máximo)**:
   - Convertir cada candidato a `float` (limpiando puntos de miles y estandarizando la coma decimal).
   - Retornar el valor máximo (`max(valores)`) para reflejar el límite máximo de financiamiento.
3. **Registro en Metadatos (Trazabilidad)**:
   - El monto seleccionado (`monto_val`) será persistido en el campo principal `monto` de la Convocatoria.
   - El rango original completo se guardará en el diccionario de `metadatos` (e.g. `metadatos["monto_rango_original"] = raw_monto`) para conservar la semántica completa y permitir visualizaciones detalladas en el frontend SPA.

---

## 7. GAPS DE TEST (Fase 6)

- **GAP-001**: `src/infra/notifications/telegram_adapter.py`
  - *Escenario*: Caída de Telegram API (Http 429 o 5xx).
  - *Riesgo*: ALTO (pérdida silenciosa de alertas críticas).
  - *Test Recomendado*: Integración/Mock con simulación de fallos HTTP y verificación del mecanismo de retry.
- **GAP-002**: `src/core/application/normalizer.py`
  - *Escenario*: Normalización de fechas de cierre representadas en texto ambiguo ("Hoy", "Hasta agotar stock").
  - *Riesgo*: MEDIO (errores de casteo que forzarían estados incorrectos).
  - *Test Recomendado*: Unitario de parsing con casos de borde de texto chileno informal.

---

## 8. PLAN DE CORRECCIÓN PRIORIZADO (Fase 7)

### Bloque 1: Corrección de Bloqueantes e Errores de Mypy/Ruff (Alta Prioridad)
- **ISSUE-001**: Corrección de `_ensure_startup_schema` inexistente en los archivos de tests unitarios ([tests/unit/test_api.py](file:///home/manager/Sync/python_proyects/grant_pulse/tests/unit/test_api.py) y [tests/unit/test_healthcheck.py](file:///home/manager/Sync/python_proyects/grant_pulse/tests/unit/test_healthcheck.py)).
- **ISSUE-002**: Corrección del error de tipado en `src/core/application/normalizer.py:493` (`limite_cierre < now`).
- **ISSUE-003**: Supresión/resolución de los warnings de asignaciones `None` en módulos opcionales (`jellyfish`, `aiosmtplib`, `HTMLParser`, `markdownify`) mediante comentarios de ignore para Mypy.
- **ISSUE-004**: Remoción de imports huérfanos en `src/infra/maintenance.py` (evita también warnings e incompatibilidades potenciales de runtime).

### Bloque 2: Reparación de Incidencias Operativas (Logs de Producción)
- **ISSUE-005**: Exposición de `/debug/wipe` en producción (`src/presentation/api/routes.py`). Condicionar el endpoint para que solo sea accesible en entornos de desarrollo (`settings.ENV != "prod"`), evitando wipes accidentales en producción.
- **ISSUE-006**: Fallos en la extracción y normalización de `monto` (`src/core/application/normalizer.py`).
  - *Problema*: La regex se aplica a textos ya extraídos limpios (que no tienen el prefijo `Montos:`), fallando la validación. Asimismo, `_parse_float` falla ante montos con caracteres como `$` o descritos como rangos (`$1.000.000 hasta $6.000.000`).
  - *Corrección*: Añadir un fallback robusto en `_apply_regex` para `monto` en caso de que falle la regex completa, y robustecer `_parse_float` para que limpie caracteres no numéricos y retorne el valor máximo al procesar rangos.
- **ISSUE-007**: Error de importación de `clean_expired_convocatorias` en `src/infra/cli.py` por presencia de imports redundantes que asocian normalizadores en `src/infra/maintenance.py`. Remover el import no utilizado `_infer_region_with_llm` en `maintenance.py` para erradicar cualquier drift o import circular en runtime.

---

## 9. DEUDA TÉCNICA RESIDUAL

- Cobertura baja en la capa de presentación/rutas (`routes.py` con 13%) y adaptadores de comunicación (`telegram_adapter.py` con 33%).
- Dependencia estructural de un único contenedor Postgres sin failover nativo en local.
