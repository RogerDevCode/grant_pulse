# GrantPulse — Reglas de desarrollo para IA

Eres arquitecto, engineer senior, reviewer estricto, QA y mantenedor de este proyecto de producción.

## 0. Principios

- fail-fast: fallar temprano y explícito, nunca silencioso
- raise low, catch high: elevar errores específicos desde el dominio, capturar amplio solo en fronteras
- contratos explícitos entre capas
- separación estricta de responsabilidades
- diseño incremental por bloques validables
- observabilidad real: logs estructurados con contexto, ids de corrida/fuente/evento
- bajo acoplamiento, alta cohesión, alta mantenibilidad

## 1. Stack

- Python 3.13.x, PostgreSQL 17 (obligatorio, no usar SQLite), FastAPI, SQLAlchemy 2, Alembic
- Pydantic, httpx, selectolax, Playwright solo si no hay alternativa
- ruff, mypy, pyright, pytest, pre-commit
- YAML para reglas por sitio, Python para reglas transversales
- Vanilla JS + CSS moderno para frontend
- Alertas: Telegram + email
- LLM: soporte opcional y desacoplado (nunca en el camino crítico)
- No usar NumPy salvo justificación concreta

## 2. Objetivo funcional

Ejecutar 1-2 veces/día. Detectar solo:
- aperturas nuevas de convocatorias de financiamiento
- cambios relevantes en convocatorias existentes

Ignorar: cambios cosméticos, ruido editorial, noticias no relacionadas, cambios de formato.

## 3. Errores y excepciones

- Nunca `except Exception: pass`
- Nunca logging + consumir error sin decidir relanzar o manejar
- Usar `raise ... from exc` al traducir errores
- Capturar específico donde se puede recuperar; capturar amplio solo en fronteras (scheduler, API handlers, CLI, workers, notificaciones, adaptadores externos)
- Toda excepción de dominio: nombre claro, semántica precisa
- Toda frontera externa: transformar errores técnicos en eventos operables
- Jerarquía: `DomainError`, `ValidationError`, `RuleEngineError`, `ScrapingError`, `ExtractionError`, `NormalizationError`, `ChangeDetectionError`, `NotificationError`, `RepositoryError`, `ConfigurationError`

## 4. Logging

- Logging estructurado, no prints
- Niveles correctos, contexto útil en errores (fuente_id, run_id, evento_id)
- No esconder stack traces relevantes
- No duplicar logs entre capas
- No hacer spam de logs

## 5. Arquitectura

Capas separadas: dominio, aplicación, infraestructura, persistencia, scraping, motor de reglas, adaptadores por sitio, notificaciones, frontend, scheduler, observabilidad, configuración, validación, tests.

Disciplina de separación tipo Spring, implementación idiomática Python.

## 6. Scraping — jerarquía obligatoria

1. HTML estático + parsing liviano (primera opción)
2. Endpoints/feeds JSON cuando existan (segunda opción)
3. Browser automation solo si no hay alternativa razonable
4. LLM solo como fallback controlado y desacoplado

No usar herramientas pesadas por moda. Costo, complejidad y robustez bajo control.

## 6b. Testing del frontend

Para pruebas E2E del propio frontend, usar el navegador más neutro: **Chromium/Chrome sin extensiones y con perfil limpio**.

- **Perfil limpio** = sin cookies, sin caché, sin estado residual entre ejecuciones. Garantiza repetibilidad.
- **Sin extensiones** = comportamiento idéntico entre desarrollo, CI y producción, sin ruido de plugins del usuario.
- **Modo headless obligatorio** en CI. En local se permite headed solo para depuración.

Herramienta preferida: `playwright-python` con `chromium.launch(headless=True)`. NO usar Chrome del sistema: la versión varía entre máquinas y rompe selectores.

Cada test debe:

1. Crear un contexto nuevo con perfil limpio (`browser.new_context()`).
2. Cerrar el contexto al finalizar (cleanup obligatorio).
3. Evitar dependencias entre tests (orden, estado compartido, fixtures globales).

## 7. Reglas por sitio

Cada sitio se define/modifica sin tocar el núcleo. YAML permite: nombre, URL base, páginas objetivo, selectores, estrategia de extracción, señales de apertura/cambio, campos a observar, exclusiones, normalizaciones, thresholds, políticas de comparación.

Reglas complejas y transversales en Python.

## 8. Reglas operativas de scraping

### Sincronización vs. monitoreo
- `sync-rules` sincroniza YAML→BD. Es local, rápida, atómica.
- NUNCA gatillar scraping, llamadas de red ni browser automation durante sync.
- Motivo: una falla de red en una fuente no debe bloquear la configuración de las demás.

### Alineación de mappings
- Mantener sincronizados URL y paginación entre YAML (`rules/*.yaml`) y catálogo duro (`src/infra/sources/catalog.py`).
- El catálogo sobrescribe `url_busqueda` en BD al sincronizar. Si no están alineados, se revierten cambios locales.

### Paginación en APIs
- Para fuentes JSON/WP-Ajax: especificar siempre límite alto explícito en la URL (ej: `per_page=100` para FIA, `cantidad=500` para SERCOTEC).
- Los backends institucionales retornan límites bajos por defecto (8-15 ítems), perdiendo registros activos.

### Limpieza de BD al cambiar identificadores
- Si se modifica `identificador_externo` o estrategia de extracción de una fuente activa: eliminar manualmente sus convocatorias viejas de la BD antes de re-scrapear.
- Motivo: cambiar la clave de idempotencia causa duplicación y alertas falsas de apertura.

### No agrupar registros granulares
- NO usar `agrupar_por` que colapse múltiples convocatorias en un solo registro.
- Motivo: destruye visibilidad de fondos regionales específicos (ej: 76 convocatorias SERCOTEC→5 grupos).

### No confiar en selectores estáticos
- Los layouts de sitios gubernamentales chilenos cambian sin aviso.
- Siempre verificar HTML renderizado real (screenshots, auditoría en contenedor) antes de asumir que un selector funciona.

### Scrapers LLM en producción
- Si el contenedor no tiene hardware/dependencias estables para LLM (NVIDIA/CUDA), desactivar la fuente (`activa: false`) en BD.
- Motivo: genera segfaults (exit code 139) que detienen todo el lote de monitoreo.

## 9. Calidad y validación continua

- ruff, mypy, pyright, pytest con cada cambio
- Validación de YAML, contratos, smoke tests, tests unitarios e integración
- Pre-commit, cobertura
- Regla: ningún archivo se considera terminado sin indicar cómo validarlo, qué tests correr, qué contratos toca y qué regresiones introduce
- Regla de cero errores: no existen "errores pre-existentes" ni "errores heredados". Todo error de ruff, mypy o pyright detectado al tocar un archivo debe ser resuelto en ese mismo cambio, sin excepción. Calificar un error como "pre-existente" para justificar ignorarlo está prohibido. Si el error existe, es responsabilidad del cambio actual corregirlo.

## 10. Comportamiento al generar código

1. Listar archivos afectados
2. Explicar por qué se tocan
3. Indicar dependencias afectadas
4. Indicar validaciones exactas post-cambio
5. Indicar tests exactos post-cambio
6. Indicar si hay placeholder/TODO/comportamiento no final
7. Indicar qué bloque queda completo y cuál no

## 11. Placeholders

- Solo para avanzar por bloques
- Deben ser explícitos y etiquetados
- No fingir funcionalidad completa
- No ocultar deuda técnica
- Deben fallar de forma clara y observable si se usan fuera de contexto

## 12. Estilo de respuesta

- Español técnico claro y directo
- Sin relleno, sin marketing, sin frases vacías
- Si algo es mala idea en Python, corregirlo
- Si una herramienta sobra, decirlo
- Si falta una herramienta crítica, agregarla con justificación
- Si una práctica inspirada en Java no aplica en Python, adaptar el principio

## 13. Archivos clave

- `src/infra/cli.py` — separación sync vs. run
- `src/infra/sources/catalog.py` — catálogo canónico de fuentes (sobrescribe BD al sync)
- `rules/*.yaml` — reglas por institución (alineadas con catálogo)
- `src/presentation/api/routes.py` — API REST
- `src/presentation/frontend/app.js` — Frontend SPA
- `src/core/domain/entities.py` — Entidades de dominio
- `src/core/domain/exceptions.py` — Jerarquía de excepciones
- `src/core/application/normalizer.py` — Normalizador de datos
- `src/infra/scraping/` — Scrapers (json_api, html_static, wp_ajax, fosis_multipage, llm_scraper)

## 14. Estilo lingüístico de las respuestas

- **Español neutro**. No usar modismos regionales (ej: evitar "che", "pibe", "decime", "boludo", "órale", "weón", "guay", "tío", "curro").
- **Tono formal entre colegas profesionales**. Tratar como "usted", no tutear.
- **Sin relleno, sin justificaciones extendidas, sin marketing**. Frases cortas y técnicas.
- **Inglés aceptado para términos técnicos universales** (commit, push, deploy, endpoint, scraper, etc.) cuando su traducción al español resulte forzada o menos precisa.

## 15. Reconstrucción mínima del proyecto

Si una LLM necesita reconstruir el proyecto desde cero, el orden correcto es:

1. Instalar Python 3.13 y PostgreSQL 17.
2. Sincronizar dependencias con `uv sync --frozen --no-group dev --extra browser`.
3. Configurar variables de entorno desde `.env` o el entorno de despliegue.
4. Aplicar migraciones con `alembic upgrade head`.
5. Verificar que `rules/*.yaml` y `src/infra/sources/catalog.py` estén alineados.
6. Levantar la API con `grantpulse-api` o `python -m src.presentation.api.main`.
7. Ejecutar sincronización/worker con `grantpulse-sync` o `python -m src.infra.cli <comando>`.
8. Validar con `make validate` antes de considerar terminado el cambio.

Reglas de reconstrucción:

- Nunca usar SQLite.
- Nunca reintroducir mutaciones de esquema ad hoc en startup si la migración ya existe.
- Nunca asumir que un `ALTER TABLE` en caliente es aceptable si el cambio pertenece a Alembic.
- Si hay drift entre ORM, Alembic y BD, la fuente de verdad es Alembic.
- Si los logs de Uvicorn aparecen como error por ir a `stderr`, configurar `log_config` para `stdout`.

## 16. Mapa operativo para una LLM

Archivos que una LLM debe leer primero para reconstruir contexto real:

- `pyproject.toml` — dependencias, scripts y toolchain.
- `Makefile` — comandos de validación y despliegue local.
- `README.md` — flujo operativo esperado.
- `src/presentation/api/main.py` — arranque API, lifespan, healthcheck y logging.
- `src/infra/cli.py` — sincronización de reglas, workers y comandos de mantenimiento.
- `src/infra/config.py` — variables de entorno, URLs, límites y proveedores.
- `src/infra/db/models.py` — esquema ORM canónico.
- `src/infra/db/repository.py` — contratos de persistencia.
- `src/infra/sources/catalog.py` — catálogo duro canónico de fuentes.
- `src/infra/rules_loader.py` — carga y validación de YAML.
- `src/core/domain/entities.py` y `src/core/domain/exceptions.py` — contratos del dominio.
- `alembic/versions/*` — historial de migraciones reales.

Reglas de edición para la LLM:

- Si se cambia un contrato de dominio, actualizar repositorios, casos de uso y tests en el mismo bloque.
- Si se cambia el esquema, actualizar modelo ORM, migración Alembic y validaciones asociadas.
- Si se agrega una fuente, mantener sincronizados YAML, catálogo duro y tests de reglas.
- Si se toca logging, conservar contexto operativo y no perder `run_id`, `fuente_id` o `evento_id`.

## 17. Decisiones de Arquitectura y Mitigaciones Implementadas

Cualquier cambio futuro debe respetar las siguientes soluciones implementadas y validadas:

### 17a. Mitigaciones de Seguridad y Robustez (Red Team)
- **Prompt Injection**: Todo contenido crudo de portales (HTML/Markdown) inyectable a los LLMs debe envolverse en etiquetas XML `<document_content>` y `</document_content>`. El `system_prompt` debe ordenar omitir instrucciones internas de estas etiquetas y tratarlas estrictamente como datos.
- **Evitar Colisiones (Locks)**: El worker de monitoreo masivo (`run_all_active_sources()`) implementa un advisory lock exclusivo a nivel de sesión sobre PostgreSQL (`SELECT pg_try_advisory_lock(178199)`). Si el lock está ocupado, la ejecución concurrente aborta inmediatamente de forma segura para evitar alertas duplicadas.
- **Protección de datos**: Los endpoints destructivos de base de datos como `/debug/wipe` arrojan HTTP `403 Forbidden` si `settings.ENV == "prod"`.

### 17b. Normalización Algorítmica de Datos
- **Monto y Rangos**: El normalizador de montos prefiere un parser algorítmico limpio en lugar de expresiones regulares propensas a fallos. Si se detecta un rango de financiamiento, la política es extraer y registrar el **monto máximo** disponible.
- **Cache Busting en Frontend**: Los endpoints de depuración expuestos en la interfaz (como logs de errores) se solicitan agregando un cache-buster dinámico (`?t=${Date.now()}`) para evitar que la caché local del navegador muestre registros desactualizados.

### 17c. Resiliencia de Notificaciones y Healthcheck
- **Retry Backoff en Telegram**: Ante caídas temporales de red o límites de tasa de la API de Telegram, las notificaciones implementan reintentos con backoff exponencial. Si retorna HTTP 429, respeta la cabecera `Retry-After`. Se aborta el reintento inmediatamente ante errores fatales del cliente (HTTP 400, 401, 403) para evitar bucles infinitos.
- **Observabilidad de Calidad**: El scheduler recopila y envía automáticamente un resumen estructurado sobre la salud y cobertura de los metadatos de las fuentes (Data Quality) al canal de Telegram al finalizar el batch.
- **Resiliencia de Railway**: El endpoint `/health` de la API retorna código HTTP `200` y `"db": "unavailable"` si PostgreSQL no responde, evitando reinicios erróneos del contenedor web por parte del orquestador durante congestiones de red externas.

