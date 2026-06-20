# Prompt de Regeneración: GrantPulse

Eres un Arquitecto de Software y Desarrollador Senior. Tu misión es generar desde cero **GrantPulse**, un sistema de monitoreo, scraping y notificaciones para detectar aperturas y modificaciones en las convocatorias públicas de financiamiento estatales de Chile (CORFO, SERCOTEC, ANID, FIA, etc.).

El objetivo del sistema es ejecutarse en lotes (1-2 veces al día) para recopilar datos de fondos de financiamiento, normalizarlos, compararlos con capturas anteriores para detectar cambios relevantes (nuevos fondos o cambios de fecha/estado) y enviar notificaciones (Telegram y Email) a los suscriptores.

---

## 1. Stack Tecnológico

El proyecto está diseñado bajo una arquitectura limpia en Python, orientada a la mantenibilidad y al fail-fast.

- **Backend**: Python 3.13.x, FastAPI.
- **Base de Datos**: PostgreSQL 17/18, SQLAlchemy 2.0 (programación asíncrona mediante `asyncpg`), Alembic para migraciones.
- **Scraping e Impersonación**:
  - `selectolax` (motor de parsing HTML ultraligero y rápido en C).
  - `httpx` (cliente HTTP asíncrono).
  - `curl_cffi` (impersonación dinámica de firmas TLS/JA3 para saltar protecciones anti-bot/WAF como BigIP).
  - `playwright` (automatización de navegador real headless como último recurso JS).
- **Proceso y Tareas**: CLI mediante `argparse`, contenedores Docker Compose, init system ligero (`tini`).
- **Frontend**: Single Page Application (SPA) responsiva con HTML5 semántico, CSS moderno (Vanilla) y Vanilla JS.

---

## 2. Estructura de Directorios (Arquitectura de Capas)

La arquitectura sigue una separación estricta de responsabilidades (estilo Spring pero implementado de forma idiomática en Python):

```text
grant_pulse/
├── alembic/                  # Migraciones de base de datos
├── rules/                    # Reglas por institución en archivos YAML
├── src/
│   ├── core/
│   │   ├── domain/           # Entidades puras, excepciones y puertos (interfaces)
│   │   └── application/      # Casos de uso (orquestadores de negocio y normalizadores)
│   ├── infra/
│   │   ├── db/               # Conexión, modelos ORM de SQLAlchemy y repositorios
│   │   ├── scraping/         # Adaptadores de scraping (JSON, curl_cffi, Playwright, RSS)
│   │   ├── notifications/    # Adaptadores de comunicación (Telegram, Email, Logger)
│   │   ├── logging.py        # Configuración de logs estructurados
│   │   ├── cli.py            # Entrypoint CLI para workers en background
│   │   └── config.py         # Configuración y variables de entorno (Pydantic Settings)
│   └── presentation/
│       ├── api/              # Controladores REST de FastAPI y esquemas Pydantic
│       └── frontend/         # Archivos estáticos de la SPA (HTML, CSS, JS)
├── tests/                    # Pruebas unitarias y de integración
├── pyproject.toml            # Gestión de dependencias y scripts del proyecto con UV
├── docker-compose.yml        # Orquestación local (servicios db, api, worker)
└── Dockerfile                # Construcción multietapa (builder/runtime) optimizada
```

---

## 3. Esquema de Base de Datos (PostgreSQL)

Los modelos ORM deben ser declarativos (SQLAlchemy 2.0). A continuación se describe el esquema lógico de las tablas:

1. **`fuentes`**: Registra los portales de las organizaciones públicas.
   - `id` (UUID, PK)
   - `nombre` (String, Unique)
   - `url_base` (String)
   - `configuracion_yaml` (Text)
   - `activa` (Boolean)
   - `creado_en` / `actualizado_en` (Timestamps con Zona Horaria)

2. **`snapshots`**: Historial de capturas crudas.
   - `id` (UUID, PK)
   - `fuente_id` (UUID, FK a `fuentes.id`, CASCADE)
   - `fecha_captura` (Timestamp con Zona Horaria)
   - `contenido_crudo` (Text)
   - `screenshot_b64` (Text, Nullable, usado para Playwright)
   - `hash_contenido` (String 64)
   - `estado_ejecucion` (String)
   - `metadatos` (JSONB)

3. **`convocatorias`**: Registros actuales de los fondos de financiamiento.
   - `id` (UUID, PK)
   - `fuente_id` (UUID, FK a `fuentes.id`, CASCADE)
   - `identificador_externo` (String 255)
   - `titulo` (String 500)
   - `descripcion` (Text, Nullable)
   - `url_detalle` (String 500, Nullable)
   - `fecha_apertura` / `fecha_cierre` (Timestamps con Zona Horaria, Nullable)
   - `monto` (Numeric 15,2, Nullable)
   - `estado` (String 100, valores canónicos: `ABIERTO`, `CERRADO`, `PROXIMAMENTE`, `ADJUDICADO`, `SUSPENDIDO`, `FINALIZADO`, `DESCONOCIDO`)
   - `region` (String 100, Nullable, normalizado canónicamente)
   - `metadatos` (JSONB)
   - `creado_en` / `actualizado_en` (Timestamps con Zona Horaria)

4. **`historial_cambios`**: Registros de deltas/alertas detectados entre ejecuciones.
   - `id` (UUID, PK)
   - `convocatoria_id` (UUID, FK a `convocatorias.id`, CASCADE)
   - `snapshot_id` (UUID, FK a `snapshots.id`, RESTRICT)
   - `fecha_deteccion` (Timestamp con Zona Horaria)
   - `es_apertura` (Boolean)
   - `delta` (JSONB, almacena cambios por campo: `{"campo": "fecha_cierre", "valor_anterior": "...", "valor_nuevo": "..."}`)
   - `es_relevante` (Boolean)

5. **`config_notificaciones`**: Canales y credenciales para el envío de alertas.
   - `id` (UUID, PK)
   - `nombre` (String 100)
   - `tipo` (String 20: `TELEGRAM`, `EMAIL`)
   - `configuracion` (JSONB: tokens, chat_ids, servidores SMTP, destinatarios)
   - `activa` (Boolean)
   - `creado_en` (Timestamp con Zona Horaria)

6. **`notificaciones`**: Registro de envíos de alertas para auditoría.
   - `id` (UUID, PK)
   - `historial_cambios_id` (UUID, FK a `historial_cambios.id`, CASCADE)
   - `canal` (String 50)
   - `destinatario` (String 255)
   - `enviado_en` (Timestamp con Zona Horaria)

7. **`audit_logs`**: Logs persistentes de salud interna.
   - `id` (UUID, PK)
   - `fuente_id` (UUID, FK a `fuentes.id`, SET NULL)
   - `nivel` (String 20: `INFO`, `WARNING`, `ERROR`)
   - `modulo` (String 50: `SCRAPER`, `LLM`, `REPO`)
   - `mensaje` (Text)
   - `detalles` (JSONB)
   - `creado_en` (Timestamp con Zona Horaria)

---

## 4. Estrategia Operativa y Jerarquía de Scraping

Para asegurar robustez y optimización de costos, el sistema debe seguir una estricta jerarquía de scraping por paso para cada origen:

1. **HTML estático / API JSON (httpx)**: Primera opción. Rápida y sin carga en memoria.
2. **Endpoints/feeds JSON de WordPress (wp-json)** o llamadas AJAX (`admin-ajax.php` con nonce dinámico): Segunda opción si existe.
3. **curl_cffi (Impersonación)**: Tercera opción. Simula la firma TLS/JA3 de navegadores modernos (e.g. Chrome 120) para evitar bloqueos por cortafuegos (WAF) sin necesidad de levantar navegadores pesados.
4. **Browser Automation (Playwright Headless)**: Cuarta opción. Solo si el sitio renderiza dinámicamente con JS protegido y las llamadas previas fallan.
5. **Inferencia LLM**: Quinto paso. Como fallback desacoplado y controlado para extraer datos de textos desestructurados.

### Sincronización vs Monitoreo
- **Sincronización (`sync-rules`)**: Lee los YAML de configuración locales y sincroniza el catálogo de fuentes en la base de datos de manera atómica. **Nunca** debe iniciar llamadas de red o scraping durante este paso.
- **Monitoreo (`run-all` / `run-file`)**: Ejecuta el scraping y almacenamiento basándose en las fuentes activas en base de datos.

### Normalización de Datos Críticos
- **Regiones**: Mapear cualquier alias de texto al nombre oficial de las 16 regiones de Chile o a `"Nacional"`.
- **Estados**: Normalizar estrictamente a través de regex que contemplen variaciones en género y número (e.g., `"Abiertas"` -> `"ABIERTO"`, `"Cerrados"` -> `"CERRADO"`).

---

## 5. Algoritmo de Detección de Cambios (Change Detection)

En cada corrida de monitoreo:
1. El scraper correspondiente descarga el crudo del portal (`fetch`).
2. Se genera un hash SHA256 del contenido crudo. Si coincide con el hash del último snapshot exitoso, se asume que no hay cambios y finaliza.
3. Si el hash difiere, se procesa la extracción de items (`extract`).
4. Para cada item extraído:
   - Se busca en la base de datos por `fuente_id` e `identificador_externo`.
   - Si no existe: Se crea la convocatoria con estado `ABIERTO` y se genera un evento en `historial_cambios` marcado como `es_apertura = True`.
   - Si existe: Se comparan los campos sensibles (e.g., `fecha_cierre`, `estado`, `titulo`, `monto`).
     - Si hay un cambio en un campo sensible: Se calcula el delta y se crea un registro en `historial_cambios` (`es_apertura = False`, `es_relevante = True`). Se actualizan los datos de la convocatoria.
     - Si los cambios no son sensibles (e.g., cambios de formato en descripción o espacios en blanco): Se actualizan los datos silenciosamente sin levantar alertas (`es_relevante = False`).

---

## 6. Frontend y API REST

### Endpoints Clave
- `/api/v1/dashboard`: Retorna estadísticas acumuladas del sistema (fuentes activas, convocatorias abiertas, eventos de cambios relevantes).
- `/api/v1/convocatorias`: Retorna las convocatorias del radar. Soporta filtros dinámicos (`estado`, `fuente_id`, `region`, `search`), ordenamientos (`por_vencer`, `recientes_creacion`), límite y desplazamiento.
- `/api/v1/convocatorias/count`: Devuelve el total de convocatorias filtradas de manera idéntica al endpoint anterior (`estado`, `fuente_id`, `region`, `search`).
- `/api/v1/fuentes`: Retorna el catálogo de fuentes indicando total de convocatorias asociadas, cuántas están abiertas, cuántas cerradas y la última fecha de captura.

### Diseño y Comportamiento del Frontend SPA
- El dashboard interactivo utiliza un sistema de diseño premium, con una estética oscura y acentos cromáticos dinámicos (estilo Glassmorphism).
- **Consistencia de conteos (Radar)**: Toda búsqueda o filtro de región se propaga tanto al listado como al endpoint `/count`, asegurando que la píldora de total de resultados, los KPIs ("Activas ahora", "Cierran en 30 días", "Sin fecha cierre") y la barra de paginación se actualicen en tiempo real y guarden absoluta consistencia con la cuadrícula de tarjetas.

---

## 7. Instrucciones para la IA / LLM

Al recibir este prompt para implementar o ampliar el proyecto:
1. **Disciplina de Capas**: Asegura que el código de dominio no contenga detalles de base de datos ni librerías de red (httpx, playwright). Utiliza los puertos (interfaces abstractas) definidos en `src/core/domain/ports.py` y deja las implementaciones en `src/infra/`.
2. **Fail-Fast**: Nunca consumas errores silenciosamente. En caso de fallo de red o parsing estructural, levanta excepciones del dominio (`ScrapingError`, `ExtractionError`, `RepositoryError`).
3. **Docker Compose Volumen Seguro**: Cuando configures montajes de volúmenes de desarrollo en Compose (e.g. `.:/app`), añade siempre volúmenes anónimos para el entorno virtual (`- /app/.venv`) para evitar que el entorno virtual del host colisione y sobrescriba el entorno interno limpio del contenedor.
4. **Validación de Salud compatible**: Implementa pruebas de salud (`healthcheck`) en el compose utilizando scripts nativos de Python (`urllib.request`) para garantizar compatibilidad directa con contenedores basados en imágenes `slim` sin requerir instalar `curl` en las capas de producción.
5. **No Agrupar por Defecto**: Asegura que cada convocatoria de una región diferente del mismo instrumento se guarde como un registro independiente (usando una clave única compuesta o el id de región del portal) para evitar colapsar los fondos y ocultar el financiamiento descentralizado en regiones.
