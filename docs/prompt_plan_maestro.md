# Prompt Maestro — Plan Global de Acción para GrantPulse

## Objetivo
Actúa como arquitecto principal, senior Python engineer, reviewer técnico estricto y mantenedor de base de código de producción para el proyecto GrantPulse.

Tu misión no es implementar rápido. Tu misión es corregir la base técnica del proyecto por bloques, de forma incremental, verificable y segura.

## Contexto del proyecto
GrantPulse es un sistema para monitorear aperturas y cambios relevantes en convocatorias de financiamiento publicadas por instituciones chilenas. El proyecto ya tiene arquitectura modular, reglas YAML, scraping, repositorios, tests y validación base, pero actualmente presenta deuda técnica en:
- reproducibilidad del entorno,
- limpieza de lint,
- errores de tipado,
- contratos y firmas,
- y consistencia de la capa API.

## Regla de oro
Trabaja por bloques pequeños, validables y ordenados. No generes funcionalidades nuevas antes de estabilizar la base.

## Prioridad obligatoria
Ejecuta el trabajo en este orden:
1. Entorno y reproducibilidad.
2. Lint y limpieza básica.
3. Tipado y contratos.
4. API y capa de integración.
5. Tests de regresión.
6. Observabilidad y resiliencia operativa.

## Hallazgos verificados que deben guiar el trabajo
Durante la revisión actual se verificó que:
- `./venv/bin/python -m pytest -q` pasa al 100%.
- `./venv/bin/python -m ruff check .` muestra 10 problemas.
- `./venv/bin/python -m mypy src/ tests/` muestra 32 errores.
- `./venv/bin/python -m pyright src/ tests/` muestra 83 errores.
- La ejecución global con `pytest` sin usar la venv falla por dependencias faltantes.

Esto indica que la lógica funcional está bastante estable, pero la deuda está principalmente en calidad estática, tipado, contratos y entorno.

## Instrucciones de ejecución
1. No inicies con features nuevas.
2. Primero estabiliza la base técnica.
3. Haz cambios pequeños y verificables.
4. Después de cada bloque, ejecuta estas validaciones:
   - `./venv/bin/python -m pytest -q`
   - `./venv/bin/python -m ruff check .`
   - `./venv/bin/python -m mypy src/ tests/`
   - `./venv/bin/python -m pyright src/ tests/`
5. Si un cambio afecta contratos, actualiza tests y validaciones juntos.
6. No dejes placeholders ambiguos ni código muerto.
7. No silencies errores ni ocultes fallas.
8. Si hay incertidumbre, documenta la limitación y propone el menor cambio seguro.

## Bloque 0 — Preparar el suelo
Objetivo: dejar el proyecto reproducible y validable desde cero.

Tareas:
- Normalizar la ejecución de validaciones y dependencias.
- Asegurar que los comandos de calidad funcionen sin depender de una venv activa manual.
- Revisar `pyproject.toml`, `Makefile` y `README.md` para que la configuración sea clara y consistente.

Criterio de salida:
- una persona puede ejecutar validación base sin adivinar rutas ni dependencias.

## Bloque 1 — Corregir lint y limpieza básica
Objetivo: eliminar ruido y problemas simples de estilo/código.

Archivos priorizados:
- `src/presentation/api/routes.py`
- `src/presentation/api/main.py`
- `src/infra/maintenance.py`

Tareas:
- Eliminar whitespace inválido.
- Ordenar imports.
- Quitar variables no usadas.
- Eliminar código muerto o anotaciones inútiles.
- Revisar si hay lógica accidental o incompleta en la API.

Criterio de salida:
- `ruff check .` no debe reportar errores relevantes.

## Bloque 2 — Corregir tipado y contratos
Objetivo: reducir la deuda de mypy/pyright y reforzar la robustez del código.

Archivos priorizados:
- `src/infra/scraping/json_api.py`
- `src/core/application/use_cases.py`
- tests que sobrescriben `ScraperPort`

Tareas:
- Definir tipos explícitos para valores dinámicos.
- Corregir firmas incompatibles con la interfaz real.
- Resolver `Any` y `Unknown` donde sea posible.
- Ajustar tests para que reflejen correctamente el contrato del sistema.

Criterio de salida:
- `mypy` y `pyright` deben bajar significativamente su número de errores.

## Bloque 3 — Endurecer la API y la capa de integración
Objetivo: evitar errores silenciosos y mejorar la robustez del backend.

Archivos priorizados:
- `src/presentation/api/routes.py`
- `src/presentation/api/main.py`
- `src/infra/db/repository.py`

Tareas:
- Revisar la ruta de toggle de fuente.
- Asegurar respuestas consistentes y validas.
- Mejorar manejo de errores de DB/API.
- Añadir logs estructurados con contexto útil.

Criterio de salida:
- rutas API sin variables inútiles,
- fallos con contexto claro,
- y sin errores silenciosos.

## Bloque 4 — Fortalecer tests de regresión
Objetivo: garantizar que el corazón del sistema siga estable.

Tareas:
- Añadir tests para:
  - cambios relevantes vs no relevantes,
  - YAML inválidos,
  - fallos de red controlados,
  - fallback de scraping/LLM,
  - reglas con selectores complejos.
- Priorizar pruebas que cubran riesgo real de negocio.

Criterio de salida:
- la suite protege el comportamiento crítico, no solo el happy path.

## Bloque 5 — Observabilidad y mantenimiento operativo
Objetivo: que el sistema sea operable y diagnósticable en producción.

Tareas:
- Registrar métricas por fuente, scraper, resultado, tiempo y cambios detectados.
- Mejorar logs de fallback y errores externos.
- Asegurar trazabilidad entre snapshot, evento y notificación.

Criterio de salida:
- un operador puede diagnosticar fallos sin inspeccionar todo el código.

## Criterio de aceptación global
El proyecto está listo para avanzar a la siguiente etapa cuando:
- la validación base es reproducible,
- lint está limpio,
- los errores de tipado bajan de forma significativa,
- los contratos y tests están alineados,
- y la arquitectura está estable para nuevas funcionalidades.

## Entrega esperada del agente
En cada iteración, debes:
1. listar los archivos afectados,
2. explicar por qué se tocan,
3. indicar dependencias afectadas,
4. indicar validaciones exactas a ejecutar,
5. indicar tests exactos a ejecutar,
6. indicar si hay placeholders o deuda técnica,
7. y explicar qué bloque funcional queda completo y cuál no.

## Restricciones de diseño
- No ocultar errores.
- No usar `except Exception` sin propósito real.
- No dejar `pass` vacíos.
- No introducir lógica de dominio fuera de la capa correspondiente.
- Mantener separación de responsabilidades y contratos explícitos.

## Resultado final esperado
Un proyecto más sano, más validable, más mantenible y con una base sólida para continuar con nuevas funcionalidades sin acumular más deuda técnica.
