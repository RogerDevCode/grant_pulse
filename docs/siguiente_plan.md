# Siguiente plan de ejecución

Estado: borrador operativo.  
Objetivo: dejar el sistema listo para monitorear instituciones chilenas de financiamiento con URLs y perfiles institucionales hardcodeados, DI explícita, fallback LLM controlado y validación continua.

## Restricciones no negociables
- No descubrir instituciones dinámicamente fuera del registry duro.
- No ocultar errores con `pass`, logs vacíos o `except Exception` genérico fuera de fronteras externas.
- No simular funcionalidad incompleta como si estuviera lista.
- No mover la lógica de dominio a la infraestructura.
- No romper el contrato de `Fuente`, `RulesConfig`, `ScraperPort`, `NotificationPort` ni los repositorios existentes.

## Modelos Groq a usar
- `llama-3.1-8b-instant`
- `qwen/qwen3-32b`
- `llama-3.3-70b-versatile`

Nota: la documentación oficial de Groq muestra estos modelos en el catálogo y documenta que la cuenta Free tiene rate limits y restricciones. La disponibilidad exacta por cuenta depende de permisos y tier; por eso el código debe tratar `403`, `429`, `502`, `503` y `529` como fallos de proveedor controlados.

## Checklist de ejecución

### 1) Dependencias y configuración
- [ ] Añadir `groq` como dependencia runtime en `pyproject.toml`.
- [ ] Añadir `pytest-cov` y `pre-commit` como dependencias de desarrollo.
- [ ] Mantener `pydantic`, `httpx`, `selectolax`, `markdownify`, `playwright`, `sqlalchemy`, `asyncpg`, `aiosmtplib`, `fastapi`, `uvicorn`, `structlog`, `pyyaml` y `respx` como parte del stack base.
- [ ] Extender `src/infra/config.py` con settings explícitos para Groq y selección de proveedor LLM.
- [ ] Mantener el contexto LLM alrededor de `100_000` caracteres y aplicar límites de salida/timeout por proveedor.

### 2) Proveedor LLM y DI
- [ ] Introducir un factory explícito para elegir proveedor LLM por configuración.
- [ ] Implementar soporte Groq con cliente oficial o adaptador OpenAI-compatible, sin romper el cliente actual de OpenRouter.
- [ ] Hacer que `LlmScraper` reciba el cliente LLM por inyección de dependencias.
- [ ] Mantener fallback de modelos por proveedor y rate limiting independiente por proveedor.
- [ ] Preservar el contrato de `extract_from_html()` y `discover_funding_url()`.

### 3) Registry duro de instituciones
- [ ] Mantener las instituciones fijas en `src/infra/sources/catalog.py`.
- [ ] Corregir las URLs canónicas cuando una institución tenga mejor URL oficial conocida.
- [ ] No introducir discovery web dinámico para encontrar instituciones.
- [ ] Asegurar que el pipeline compuesto use el profile duro cuando exista.

### 4) YAML por sitio
- [ ] Agregar `rules/subdere.yaml`.
- [ ] Agregar `rules/economia.yaml`.
- [ ] Agregar `rules/bancoestado.yaml`.
- [ ] Usar selectores concretos por sitio, con `self` y `attr:` donde aporten valor.
- [ ] Mantener compatibilidad con `RulesConfig` y validación estricta de YAML.

### 5) Scraping robusto por institución
- [ ] Endurecer `CompositeFundingScraper` con DI explícita para fetchers, LLM y sleep.
- [ ] Registrar métricas de ejecución por paso, fuente y fallback.
- [ ] Fallar rápido ante errores no esperados; solo hacer fallback para errores de scraping controlados.
- [ ] Añadir pausa mínima y jitter entre requests para evitar rate limits.
- [ ] Reforzar recuperación estática antes de browser automation y LLM.

### 6) Selectores y contexto
- [ ] Permitir `self` como selector lógico en el extractor estático.
- [ ] Permitir `attr:` en más de un campo cuando el sitio lo necesite.
- [ ] Mejorar el contexto Markdown para el LLM sin superar el presupuesto de caracteres.
- [ ] Priorizar nodos relevantes y descartar ruido visual o editorial.

### 7) Tests y validación
- [ ] Agregar tests para los YAML nuevos.
- [ ] Agregar tests para `self` y `attr:` en el scraper estático.
- [ ] Agregar tests para el factory de LLM y el provider Groq cuando corresponda.
- [ ] Agregar tests para métricas y fallback del pipeline compuesto.
- [ ] Validar con `py_compile`, `pytest`, `ruff`, `mypy` y `pyright` cuando el entorno tenga las dependencias instaladas.

## Criterio de cierre
El bloque se considera listo solo si:
- las URLs institucionales están hardcodeadas en el registry,
- los YAML nuevos cargan sin errores,
- el pipeline compuesto registra métricas y fallback explícitos,
- el LLM queda desacoplado por DI,
- y la validación automática no deja errores ocultos.
