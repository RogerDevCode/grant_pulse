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

- Python 3.13.x, PostgreSQL 17, FastAPI, SQLAlchemy 2, Alembic
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
