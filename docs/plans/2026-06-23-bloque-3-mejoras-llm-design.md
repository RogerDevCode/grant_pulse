# Bloque 3: plan detallado de mejoras para LLM

## Objetivo
Hacer que el uso de LLM en GrantPulse sea:
- opcional,
- desacoplado del camino crítico,
- medible en costo y calidad,
- recuperable ante fallos,
- y seguro frente a cambios de esquema o de proveedor.

El LLM debe resolver tareas de frontera, no sostener el flujo principal:
- auto-healing de selectores,
- descubrimiento de URLs de financiamiento,
- extracción profunda opcional,
- enriquecimiento de detalles,
- ayuda semántica cuando el HTML o JSON no alcancen.

## Estado actual
La base ya tiene varios proveedores y rutas:
- `CommandCode`
- `OpenRouter`
- `Groq`
- `NVIDIA`
- cliente de failover
- extracción desde HTML y desde detalle
- discovery de URL
- healing de selectores

También existen protecciones útiles:
- límite de caracteres de contexto,
- rate limiting,
- fallback de modelos,
- validación de JSON de salida,
- normalización de payloads,
- manejo de errores por frontera.

El problema actual no es ausencia de features. El problema es que la superficie LLM todavía mezcla:
- selección de proveedor,
- construcción de prompt,
- parsing,
- fallback,
- compatibilidad con dependencias opcionales,
- y reglas de negocio.

Eso obliga a endurecer el diseño para que siga siendo utilizable cuando falte una dependencia, una API key o un modelo.

## Recomendación
Separar el bloque LLM en cuatro responsabilidades:

1. **Selección de proveedor**
   - Resolver qué backend usar.
   - Mantener prioridad configurable.
   - Permitir auto, pero con reglas explícitas.

2. **Construcción de contexto**
   - Preparar HTML, Markdown, screenshots y metadata.
   - Recortar ruido.
   - Controlar presupuesto de tokens o caracteres.

3. **Extracción y validación**
   - Ejecutar prompts.
   - Normalizar el resultado.
   - Validar contrato de salida.
   - Rechazar salidas ambiguas.

4. **Gobernanza operativa**
   - Telemetría por proveedor y modelo.
   - Costo estimado por corrida.
   - Reintentos y rotación de modelos.
   - Circuito de degradación si el proveedor falla.

## Alternativas evaluadas
### Opción A: mantener el cliente monolítico y agregar más reglas
Ventaja:
- mínimo cambio inmediato.

Desventaja:
- el módulo crece sin control,
- los fallos opcionales se vuelven más difíciles de aislar,
- se complica el mantenimiento por proveedor.

### Opción B: descomponer el cliente en pipeline LLM por etapas
Ventaja:
- mejor separación de responsabilidades,
- más fácil de testear,
- más simple introducir nuevos proveedores o prompts.

Desventaja:
- requiere refactor de varias funciones.

### Opción C: mover el LLM a un servicio externo dedicado
Ventaja:
- aislamiento fuerte,
- mejor para equipos grandes.

Desventaja:
- demasiado complejo para el estado actual,
- introduce infraestructura innecesaria.

**Recomendación:** Opción B. Es la forma correcta de endurecer el cliente sin sobrediseñar.

## Componentes propuestos
### 1. `LLMContextBuilder`
Responsabilidad:
- construir el contexto de entrada para cada tarea,
- limpiar HTML,
- generar Markdown,
- compactar nodos relevantes,
- adjuntar screenshot cuando aporte valor.

Debe fallar explícitamente si no puede producir un contexto utilizable.

### 2. `LLMProviderRouter`
Responsabilidad:
- elegir proveedor y modelo,
- aplicar prioridad por entorno,
- respetar variables de configuración,
- rotar ante errores transitorios.

Debe poder operar con:
- modo `auto`,
- proveedor fijo,
- fallback con lista explícita.

### 3. `LLMResponseValidator`
Responsabilidad:
- extraer JSON del texto crudo,
- validar tipos,
- validar campos requeridos,
- rechazar respuestas truncadas o no estructuradas.

Debe distinguir:
- respuesta vacía,
- respuesta no JSON,
- respuesta JSON pero inválida,
- respuesta JSON válida pero semánticamente inservible.

### 4. `LLMUsageTracker`
Responsabilidad:
- registrar proveedor, modelo, tiempo, tamaño de contexto y estado,
- estimar costo o al menos exponer contadores operativos,
- marcar fallos por timeout, rate limit, parsing, cuota o red.

## Mejoras técnicas recomendadas
### Selección de proveedor
- Mantener `auto`, pero con orden y prioridad explícitos.
- No mezclar selección con extracción.
- Permitir override por fuente si un sitio requiere un proveedor particular.

### Prompting
- Centralizar plantillas.
- Usar plantillas declarativas por caso:
  - `extract_from_html`
  - `extract_single_detail`
  - `discover_funding_url`
  - `heal_selectors`
- Separar prompt de sistema y prompt de usuario.
- Mantener schema estricto por caso de uso.

### Parsing
- Validar JSON con estrategia por capas:
  - JSON puro,
  - JSON dentro de bloque markdown,
  - extracción de objeto/array embebido.
- Rechazar respuestas parciales o sin estructura mínima.

### Guardrails
- Límite de contexto por tarea.
- Límite de output tokens.
- Límite de reintentos por solicitud.
- Rate limit por proveedor.
- Backoff con jitter.
- Registro de `preview` controlado, nunca dumps completos innecesarios.

### Aislamiento de dependencias
- `selectolax`, `markdownify`, `respx` y similares no deben romper importación de módulos no-LMM.
- Cuando falte una dependencia de soporte, la ruta LLM debe fallar con error explícito si se invoca.
- El resto del sistema debe seguir operando.

## Modelo operativo propuesto
### Camino normal
1. Fetcher principal obtiene HTML o JSON.
2. El pipeline estructurado intenta resolver el caso sin LLM.
3. Si falla el selector o la semántica de la respuesta:
   - se usa LLM como fallback.
4. El resultado se valida.
5. Si pasa, se persiste.

### Camino de degradación
1. Falla proveedor primario.
2. Falla rotación.
3. Falla parseo.
4. Se registra evento con causa concreta.
5. El pipeline sigue solo si existe otro camino no-LMM razonable.

### Camino de exclusión
Si el entorno no tiene:
- API key,
- binario requerido,
- o librerías necesarias,

entonces la funcionalidad LLM se marca no disponible sin bloquear la aplicación.

## Validación y testing
### Tests unitarios
- selección de proveedor,
- rotación de modelos,
- extracción de JSON,
- validación de payloads,
- fallos por dependencia faltante,
- fallos por timeout y rate limit.

### Tests de integración
- proveedor real o mockeado con respuesta válida,
- provider failover,
- response parsing con ruido,
- healing de selectores,
- discovery de URL.

### Smoke tests
- arranque de API sin LLM disponible,
- worker de scraping sin credenciales LLM,
- rutas de fallback sin provider.

## Métricas mínimas
Registrar por corrida:
- proveedor usado,
- modelo usado,
- número de intentos,
- tiempo total,
- tamaño del contexto,
- tokens de salida si el proveedor los expone,
- éxito o error,
- tipo de error,
- si el resultado fue por fallback o ruta primaria.

## Plan por fases
### Fase 1
- Extraer constructor de contexto.
- Centralizar prompts.
- Normalizar validación de respuesta.
- Reducir imports opcionales al borde.

### Fase 2
- Separar proveedor/router de parsing.
- Introducir telemetría de uso.
- Endurecer fallos semánticos.

### Fase 3
- Permitir overrides por fuente.
- Mejorar rotación y circuit breaker.
- Medir costo y calidad por proveedor.

## Criterios de aceptación
El bloque LLM se considera correcto cuando:
- la app arranca sin LLM instalado,
- la app arranca sin claves LLM,
- una falla LLM no rompe el scraping principal,
- los prompts están centralizados y testeados,
- la respuesta inválida se rechaza explícitamente,
- el costo y la calidad son visibles por corrida y por fuente.

## Riesgos
- Sobreusar LLM donde bastaba HTML/JSON.
- Crear demasiadas variantes de prompt sin métricas.
- Convertir el healing en un parche permanente.
- Hacer que el proveedor sea un cuello de botella de arranque.

## No objetivos
- No mover LLM al camino crítico.
- No hacer fine-tuning en esta fase.
- No introducir un servicio LLM separado todavía.
- No sumar más complejidad de proveedor sin métricas de uso.

