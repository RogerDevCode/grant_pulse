# Bloque 2: plan de mejora de scraping y escalamiento

## Objetivo
Reducir fragilidad, costo operativo y acoplamiento del sistema de scraping, manteniendo la política del proyecto:
- HTML estático primero.
- JSON / RSS / AJAX como segunda opción.
- Browser automation solo como fallback.
- LLM solo como último recurso, desacoplado del camino crítico.

El objetivo funcional es detectar nuevas aperturas y cambios relevantes con menos falsos negativos, menos ruido y mejor capacidad de crecer por fuente, por corrida y por volumen de datos.

## Diagnóstico actual
La base técnica ya cubre varios caminos:
- `httpx` + `selectolax` para HTML.
- `curl_cffi` para sitios con fricción anti-bot.
- `trafilatura` como heurística de respaldo.
- `Playwright` para casos complejos.
- `LLM` para extracción y auto-healing.

El problema no es ausencia de herramientas. El problema es coordinación:
- Hay demasiada lógica de fallback embebida en objetos grandes.
- El pipeline mezcla fetch, extracción, fusión, auto-healing y persistencia operacional.
- La concurrencia está fija en código en algunos puntos.
- La observabilidad existe, pero no cuantifica bien cuándo una fuente degrada o cuándo un fallback empieza a dominar.
- El escalamiento horizontal no está protegido por un mecanismo explícito de leasing o claim de fuentes.

## Recomendación
Adoptar una arquitectura en tres capas:

1. **Capa de adquisición**  
   Fetchers pequeños y especializados por estrategia:
   - `json_api`
   - `wp_ajax`
   - `rss_feed`
   - `html_static`
   - `curl_cffi`
   - `browser`

2. **Capa de resolución de fuente**  
   Un orquestador por fuente que solo decide:
   - qué paso ejecutar,
   - qué fallback intentar,
   - cuándo cortar,
   - cómo registrar métricas.

3. **Capa de ejecución distribuible**  
   Workers independientes para:
   - monitoreo principal,
   - reintentos,
   - enriquecimiento,
   - auto-healing de selectores,
   - tareas de mantenimiento.

La recomendación es mantener PostgreSQL como coordinador inicial antes de introducir cola externa. Primero conviene resolver el “claim” de trabajo con la infraestructura ya existente.

## Alternativas evaluadas
### Opción A: refactor incremental sobre el pipeline actual
Ventaja:
- menor costo inmediato,
- menos riesgo,
- reutiliza lo existente.

Desventaja:
- el pipeline grande sigue creciendo,
- el escalamiento sigue limitado por acoplamiento.

### Opción B: orquestador por fuente + workers con leasing en PostgreSQL
Ventaja:
- mejora fuerte en escalabilidad,
- evita doble procesamiento,
- mantiene dependencia única en PostgreSQL.

Desventaja:
- requiere contrato de leasing y expiración,
- obliga a tocar más capas.

### Opción C: cola externa dedicada
Ventaja:
- excelente para escalar en paralelo.

Desventaja:
- mayor complejidad operativa,
- más infraestructura,
- no es necesaria todavía.

**Recomendación:** Opción B. Es el mejor punto de equilibrio entre robustez, costo y complejidad.

## Componentes propuestos
### 1. Fuente de verdad de estrategia
Mantener el YAML como contrato por sitio, pero limitar su responsabilidad a:
- URLs,
- selectores,
- estrategia base,
- exclusiones,
- normalizaciones,
- thresholds,
- fallbacks por sitio.

La lógica transversal debe vivir en Python.

### 2. Orquestador de scraping
Un servicio de aplicación que reciba una fuente y produzca un resultado tipado:
- snapshot,
- items extraídos,
- métricas de paso,
- trazas de fallback,
- estado final.

Debe devolver errores explícitos, no mezclar silenciosamente “vacío” con “falló”.

### 3. Leasing de trabajo
Agregar un lease por fuente o por tarea en PostgreSQL:
- un worker reclama una fuente,
- el lease vence si el worker cae,
- otro worker puede retomarla,
- se evita ejecución duplicada en horizontal.

### 4. Telemetría operativa
Registrar por corrida y por fuente:
- estrategia usada,
- paso inicial,
- número de fallbacks,
- tiempo por fetch,
- tiempo por extracción,
- ratio de items descartados,
- ratio de auto-healing,
- ratio de error por fuente.

### 5. Cliente HTTP reutilizable
Usar clientes HTTP con ciclo de vida controlado por worker o por corrida:
- reduce overhead,
- mejora pool reuse,
- facilita timeouts y retries uniformes.

## Técnicas de scraping a reforzar
### HTML estático
- Mantener `selectolax` como parser primario.
- Agregar validación más agresiva de selectores.
- Introducir umbrales de calidad por fuente:
  - si demasiados items fallan, cortar con error de extracción.

### JSON / APIs
- Validar contrato de respuesta antes de iterar.
- Paginación explícita y límite máximo por fuente.
- Falla explícita si el root path deja de devolver lista.

### AJAX / WordPress
- Encapsular nonce discovery por fuente.
- Reintentar con backoff corto si el nonce caducó.
- Separar error de red, error de JSON y error de estructura HTML.

### Browser automation
- Mantenerlo como fallback.
- Usar perfil limpio y headless.
- Reutilizarlo solo para fuentes donde el DOM final sea imprescindible.

### LLM
- Limitarlo a:
  - auto-healing de selectores,
  - descubrimiento de URL de convocatorias,
  - extracción profunda opcional.
- Nunca en el camino crítico.
- Si faltan dependencias o API key, el sistema debe seguir operando sin esa ruta.

## Librerías a considerar
Sin introducir peso innecesario, las candidatas de mayor retorno son:
- `tenacity` para retries con backoff controlado.
- `aiolimiter` para rate limiting por dominio o por fuente.
- `async-lru` solo si aparece repetición real de resoluciones costosas.

No se recomienda sumar más parsing libraries mientras `selectolax`, `trafilatura` y `httpx` cubran la necesidad real.

## Errores y fallback
Reglas:
- fetch error: propagar como error operativo.
- extraction error: propagar si rompe el contrato del sitio.
- empty result: solo aceptar como éxito si el sitio lo declara explícitamente vacío.
- partial item error: permitido solo si queda claro el umbral y se registra la pérdida.
- fallback success: registrar el paso exacto que salvó la corrida.

No se debe normalizar un fallo estructural como “warning y seguir” si eso oculta pérdida de cobertura.

## Escalamiento
### Corto plazo
- Parametrizar concurrencia por entorno.
- Reutilizar clientes HTTP.
- Registrar métricas de degradación por fuente.
- Separar importación lazy de dependencias no críticas.

### Mediano plazo
- Introducir lease en PostgreSQL.
- Separar workers de monitoreo, enriquecimiento y mantenimiento.
- Hacer que la API no ejecute bootstrap pesado salvo migraciones y sync mínimo.

### Largo plazo
- Pasar a cola externa si el volumen de fuentes o reintentos lo exige.
- Mantener contratos tipados entre cola, worker y persistencia.

## Fases
### Fase 1
- Medir y registrar mejor.
- Parametrizar concurrencia.
- Reforzar umbrales de falla.
- Reutilizar clientes HTTP.

### Fase 2
- Introducir leasing en PostgreSQL.
- Separar workers de monitoreo y mantenimiento.
- Reducir el pipeline grande a orquestador + fetchers.

### Fase 3
- Extraer tareas a cola externa si el crecimiento lo justifica.
- Optimizar recuperación y reintentos por dominio.

## Criterios de aceptación
El bloque 2 se considera correcto cuando:
- una fuente degradada no oculta su error,
- un fallback exitoso queda registrado con trazabilidad,
- el worker puede escalar sin duplicar tareas,
- la concurrencia se puede ajustar sin tocar código,
- los imports opcionales no rompen el arranque,
- el scraper sigue priorizando HTML estático y JSON antes de browser o LLM.

## Riesgos
- Introducir leasing sin expiración correcta puede bloquear fuentes.
- Hacer demasiado granular el orquestador puede aumentar complejidad sin beneficio.
- Elevar umbrales de calidad demasiado pronto puede cortar fuentes útiles.

## No objetivos
- No introducir cola externa en esta fase.
- No reemplazar el stack actual de parsing.
- No mover LLM al camino crítico.
- No agregar browser automation adicional.

