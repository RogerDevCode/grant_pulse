Actúa como arquitecto principal del proyecto, senior Python engineer, reviewer técnico estricto, QA engineer y mantenedor de una base de código de producción.

Quiero que diseñes y generes un sistema serio, escalable y mantenible para monitorear aperturas y cambios relevantes en mensajes o convocatorias de financiamiento publicados en sitios web de instituciones chilenas como CORFO, Sercotec, FIA, ANID, AgenciaSE y otras similares.

Tu prioridad no es escribir código rápido.
Tu prioridad es construir una base correcta, extensible, validable y resistente a errores.

==================================================
0. PRINCIPIOS RECTORES
==================================================
Debes trabajar con estos principios:

- fail-fast
- errores nunca silenciosos
- propagación explícita de errores
- validación continua tras cada cambio
- diseño por bloques incrementales
- placeholders controlados solo cuando sean necesarios
- contratos explícitos entre capas
- separación estricta de responsabilidades
- alta mantenibilidad
- bajo acoplamiento
- alta cohesión
- observabilidad real
- posibilidad de reemplazar adaptadores, scrapers, reglas y notificaciones sin romper el núcleo

Si detectas una mala decisión en mi planteamiento, corrígela y explica por qué.

==================================================
1. STACK OBLIGATORIO
==================================================
- Python 3.13.x
- PostgreSQL 17
- HTML
- CSS moderno
- Vanilla JavaScript
- scripts JS puntuales si el frontend lo requiere
- tipado estricto
- ruff
- mypy
- pyright
- pytest
- validación continua después de crear o modificar archivos
- reglas por sitio en YAML
- reglas generales en Python
- frontend versátil y completo
- alertas por Telegram e email
- soporte opcional y desacoplado para LLM
- uso de librerías especializadas cuando aporten valor real, por ejemplo numpy u otras, pero solo si hay una necesidad concreta y justificada

==================================================
2. OBJETIVO FUNCIONAL
==================================================
El sistema debe ejecutarse 1 o 2 veces al día y detectar solamente:
- aperturas nuevas de convocatorias, fondos o mensajes de financiamiento
- cambios relevantes en mensajes o convocatorias de financiamiento existentes

Debe ignorar:
- cambios cosméticos del HTML
- ruido editorial
- noticias no relacionadas
- cambios irrelevantes de formato
- elementos decorativos del sitio

==================================================
3. ESTILO DE DESARROLLO
==================================================
Quiero desarrollar por bloques, de forma incremental.

Eso implica:
- primero estructura y contratos
- luego implementaciones base
- luego placeholders controlados donde todavía falte lógica
- luego desarrollo progresivo de cada bloque
- luego endurecimiento con validaciones, tests y refinamiento

Cada bloque debe quedar utilizable, validable y coherente antes de pasar al siguiente.

No quiero generación masiva de archivos sin control.
No quiero que escribas 40 archivos de una vez si no se pueden validar razonablemente.
Quiero iteraciones pequeñas, seguras y comprobables.

==================================================
4. MANEJO DE ERRORES Y EXCEPCIONES
==================================================
Quiero que el proyecto siga una política estricta de manejo de errores.

Debes aplicar estas reglas:

- fail-fast cuando una precondición crítica no se cumple
- nunca silenciar errores
- si capturas una excepción, debes:
  - manejarla de verdad, o
  - loguearla con contexto útil, y
  - volver a elevarla o traducirla a una excepción de dominio apropiada
- usar excepciones específicas cuando exista un caso conocido
- evitar catch genérico salvo en los bordes del sistema
- cuando uses una captura amplia, debe ser en capas de frontera como:
  - scheduler
  - handlers de API
  - comandos CLI
  - workers
  - notificaciones
  - adaptadores externos
- si ocurre un error de infraestructura o dependencia externa:
  - registrar logs con contexto
  - preservar la traza
  - usar raise desde la excepción original cuando corresponda
- evitar errores silenciosos
- evitar pass vacíos
- evitar except Exception sin propósito claro
- evitar usar excepciones como control de flujo normal

Quiero un enfoque inspirado en robustez enterprise:
- las funciones deben dejar claro qué errores pueden propagar
- el caller debe estar obligado por diseño a decidir si:
  - deja propagar
  - traduce
  - maneja
  - registra
- aunque Python no tenga checked exceptions como Java, quiero aproximar esa disciplina con:
  - excepciones de dominio bien definidas
  - jerarquías de excepciones
  - contratos explícitos
  - tipado
  - nombres claros
  - documentación breve y útil

==================================================
5. LOGGING Y OBSERVABILIDAD
==================================================
Quiero logging serio, no prints.

Debes diseñar:
- logging estructurado
- niveles correctos de log
- contexto útil en errores
- ids de corrida
- ids de fuente o sitio
- ids de evento
- trazabilidad de cambios
- auditoría mínima
- logs útiles para debugging
- logs útiles para operación

Si un error ocurre:
- registrar contexto suficiente
- no esconder stack trace cuando sea relevante
- no duplicar logs innecesariamente en varias capas
- evitar spam de logs
- luego volver a elevar o traducir el error si corresponde

==================================================
6. ARQUITECTURA ESPERADA
==================================================
Quiero una arquitectura modular por responsabilidades, con separación clara entre:
- dominio
- aplicación
- infraestructura
- persistencia
- scraping
- motor de reglas
- adaptadores por sitio
- notificaciones
- frontend
- scheduler
- observabilidad
- configuración
- validación
- tests

Inspiración:
- disciplina de proyectos Java/Spring en orden y separación
- implementación idiomática de Python moderno, sin verbosidad absurda

==================================================
7. REGLAS POR SITIO
==================================================
Cada sitio debe poder definirse o modificarse sin tocar el núcleo.

Las reglas YAML deben permitir definir:
- nombre de la fuente
- URL base
- páginas objetivo
- selectores
- estrategias de extracción
- señales de apertura
- señales de cambio relevante
- campos a observar
- exclusiones
- normalizaciones
- thresholds
- políticas de comparación

Las reglas complejas y transversales deben implementarse en Python.

==================================================
8. ESTRATEGIA DE SCRAPING
==================================================
Quiero que propongas e implementes esta jerarquía:

1. HTML estático y parsing liviano
2. endpoints o feeds cuando existan
3. browser automation solo si no hay alternativa razonable
4. LLM solo como fallback controlado y desacoplado

No quiero usar herramientas pesadas por moda.
Quiero costo, complejidad y robustez bajo control.

==================================================
9. CALIDAD Y VALIDACIÓN CONTINUA
==================================================
El proyecto debe prepararse desde el inicio para validación continua obligatoria.

Debes incorporar y configurar:
- ruff
- mypy
- pyright
- pytest
- validación de YAML
- validación de contratos
- smoke tests
- tests unitarios
- tests de integración
- pre-commit
- cobertura
- comandos de validación automáticos
- validación después de cada creación o modificación de archivos

Regla obligatoria:
ningún archivo se considera terminado si no indicas:
- cómo validarlo
- qué tests correr
- qué contratos toca
- qué riesgos de regresión introduce

==================================================
10. COMPORTAMIENTO OBLIGATORIO AL GENERAR CÓDIGO
==================================================
Cada vez que generes o modifiques código debes:

1. listar archivos afectados
2. explicar por qué se tocan
3. indicar dependencias afectadas
4. indicar validaciones exactas a ejecutar después
5. indicar tests exactos a ejecutar después
6. indicar si el cambio introduce placeholder, TODO o comportamiento aún no final
7. indicar qué bloque funcional queda completo y cuál no

No des por hecho que el cambio quedó bien sin proponer su validación.

==================================================
11. PLACEHOLDERS CONTROLADOS
==================================================
Se permite usar placeholders, pero con reglas estrictas:

- solo cuando sea útil para avanzar por bloques
- deben ser explícitos
- deben estar claramente etiquetados
- no deben fingir funcionalidad completa
- no deben ocultar deuda técnica
- deben lanzar una excepción clara o devolver un resultado explícitamente no implementado si alguien intenta usarlos fuera de contexto
- no deben quedar ambiguos

Ejemplo conceptual:
- si algo aún no está implementado, prefiero un placeholder que falle de forma clara y observable, no una simulación silenciosa

==================================================
12. DECISIONES TÉCNICAS ESPERADAS
==================================================
Quiero que tomes decisiones concretas y justificadas sobre:
- framework backend o no framework
- ORM o SQL-first
- estrategia de migraciones
- diseño de frontend
- scheduler
- estructura de módulos
- contratos
- jerarquía de excepciones
- política de logs
- motor de reglas
- persistencia de snapshots y eventos
- estrategia de notificaciones
- uso opcional de LLM
- uso de librerías especializadas cuando convenga

==================================================
13. ETAPAS DE TRABAJO OBLIGATORIAS
==================================================
### ETAPA 1
No generes código todavía.
Entrega solamente:
1. resumen ejecutivo
2. decisiones técnicas
3. arquitectura
4. modelo de dominio
5. diseño de base de datos
6. estrategia de scraping
7. estrategia de reglas YAML + Python
8. estrategia de errores, excepciones, logs y propagación
9. estrategia de validación continua
10. estrategia de testing
11. estructura de carpetas
12. riesgos técnicos
13. preguntas abiertas
14. primer bloque a implementar

### ETAPA 2
Una vez aprobada la arquitectura, genera solo el bloque inicial del proyecto:
- pyproject.toml
- tooling
- estructura mínima
- contratos base
- excepciones base
- logging base
- configuración base
- validación YAML base
- dominio base
- tests mínimos del bloque
- frontend base si corresponde

No generes más de lo que se pueda validar razonablemente en esa iteración.

### ETAPA 3 Y SIGUIENTES
Luego sigue por bloques pequeños:
- un bloque funcional por vez
- validación obligatoria tras cada bloque
- tests obligatorios tras cada bloque
- documentación técnica corta por bloque

==================================================
14. FORMATO DE RESPUESTA OBLIGATORIO
==================================================
Responde EXACTAMENTE con esta estructura:

1. Resumen ejecutivo
2. Decisiones técnicas recomendadas
3. Arquitectura propuesta
4. Modelo de dominio
5. Diseño de base de datos PostgreSQL 17
6. Estrategia de scraping recomendada
7. Estrategia de reglas YAML y reglas generales en Python
8. Estrategia de errores, excepciones, logs y fail-fast
9. Estrategia de validación continua y contratos
10. Estrategia de testing
11. Estrategia de alertas por Telegram e email
12. Estrategia de soporte LLM opcional
13. Estructura de carpetas del proyecto
14. Riesgos técnicos
15. Preguntas abiertas
16. Primer bloque que implementarías

==================================================
15. ESTILO DE RESPUESTA
==================================================
- Español técnico claro y directo
- Sin relleno
- Sin marketing
- Sin frases vacías
- Si algo es mala idea en Python, corrígelo
- Si una herramienta sobra, dilo
- Si falta una herramienta crítica, agrégala y justifica
- Si una práctica inspirada en Java no aplica literalmente en Python, adapta el principio correctamente en lugar de copiarlo mal
```

## Ajuste técnico importante
Aquí hay un punto donde conviene ser duro: **no pidas `try/except Exception` en todas partes**. Eso sería un error de diseño. En Python, la práctica sana es **capturar específico donde puedes recuperar** y **capturar amplio en la frontera** para loggear con contexto y volver a elevar, o mapear a una respuesta controlada. Eso está alineado con “raise low, catch high” y con evitar enmascarar bugs. [web:292][web:296]

## Lo que sí te recomiendo imponer
Agrega además estas reglas operativas dentro del prompt o como instrucciones adicionales:

- “Usa `raise ... from exc` al traducir errores.”
- “No hacer `except Exception: pass` jamás.” [web:294]
- “No hacer logging y consumir el error sin decidir explícitamente si se maneja o se relanza.” [web:293][web:296]
- “Toda excepción de dominio debe tener nombre claro y semántica precisa.”
- “Toda frontera externa debe transformar errores técnicos en eventos operables.”

## Sugerencias
Te sugiero estas decisiones para que la LLM no derrape:

- **No usar NumPy** salvo que realmente haya procesamiento matricial, scoring pesado o comparación numérica que lo justifique; para scraping y reglas probablemente no aporta gran cosa.
- **Sí usar Pydantic**, SQLAlchemy 2, Alembic, httpx, selectolax, pytest, structlog o logging bien configurado, y Playwright solo si toca.
- **Sí definir una jerarquía de excepciones**, por ejemplo:
  - `DomainError`
  - `ValidationError`
  - `RuleEngineError`
  - `ScrapingError`
  - `ExtractionError`
  - `NormalizationError`
  - `ChangeDetectionError`
  - `NotificationError`
  - `RepositoryError`
  - `ConfigurationError`

## Mi recomendación final
El principio correcto no es “usar Java exceptions en Python”, sino este:

- contratos claros,
- excepciones específicas,
- fallar temprano,
- log útil,
- nada silencioso,
- relanzar con contexto,
- capturar arriba donde tenga sentido operacional. [web:292][web:294][web:296]

Si quieres, en el siguiente paso te preparo algo todavía más útil: un **prompt de ETAPA 2**, para que la LLM ya te genere el **bootstrap real del proyecto** con `pyproject.toml`, `ruff`, `mypy`, `pyright`, `pytest`, `pre-commit`, jerarquía de excepciones, logging base y primer bloque validable.
