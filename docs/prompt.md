# Directrices de Contexto y Desarrollo para IA (Prompt de Siguiente Etapa)

Este documento resume las lecciones aprendidas, cambios de diseño críticos y directrices de desarrollo implementados en el proyecto **GrantPulse** durante la optimización de los pipelines de scraping y la alineación de base de datos. Debe ser cargado como contexto obligatorio para cualquier modelo o agente de IA que trabaje sobre esta base de código.

---

## 🎯 Contexto Actual del Proyecto
El sistema monitorea aperturas y cambios en convocatorias de financiamiento de instituciones chilenas (CORFO, SERCOTEC, FIA, etc.). Los perfiles de scraping están definidos en un **catálogo canónico en duro** (`src/infra/sources/catalog.py`) y en **archivos YAML de reglas** (`rules/*.yaml`), los cuales se persisten en la tabla `fuentes` de PostgreSQL.

---

## 🛠️ Lo que SE DEBE Hacer (Buenas Prácticas)

### 1. Desacoplamiento de Sincronización vs. Monitoreo
* **Acción:** La sincronización de configuraciones YAML hacia la BD (`sync-rules`) debe ser una operación local, rápida y atómica (`sync_single_source_config`).
* **Regla:** Nunca gatillar llamadas de red, simulaciones de navegador o scraping real durante el comando de sincronización de reglas. La recolección de datos es exclusiva de los comandos de ejecución (`run-file`, `run-all`).
* **Motivo:** Previene que fallas de red, selectores desactualizados o crashes graves de una sola fuente interrumpan y dejen incompleta la actualización de configuraciones del resto de las instituciones.

### 2. Alineación Estricta de Mappings
* **Regla:** Mantener sincronizada la URL y los parámetros de paginación entre los archivos de configuración YAML (`rules/*.yaml`) y el catálogo duro (`src/infra/sources/catalog.py`). 
* **Motivo:** En cada sincronización, el catálogo sobrescribe propiedades críticas como la `url_busqueda` en la BD. Si no están alineados, se revertirán los cambios locales.

### 3. Paginación y Volumen en APIs
* **Regla:** Para fuentes basadas en endpoints estructurados (`json_api`, `wp_ajax`), especificar siempre parámetros explícitos de límite alto y paginación en la URL (ej: `per_page=100` para FIA, `cantidad=500` para SERCOTEC).
* **Motivo:** Por defecto, los backends institucionales suelen retornar límites bajos (ej. 8 o 15 ítems), perdiendo la mayoría de los registros activos.

### 4. Limpieza de BD en Cambios Estructurales
* **Regla:** Si se modifica el `identificador_externo` o la estrategia de extracción de una fuente activa, se debe realizar una **eliminación manual previa de sus convocatorias antiguas** en la BD.
* **Motivo:** Al cambiar la clave de idempotencia, el pipeline no reconocerá los registros viejos, causando duplicación de datos o alertas incorrectas de apertura.

---

## ❌ Lo que NO SE DEBE Hacer (Anti-patrones a Evitar)

### 1. Agrupar Registros Granulares
* **Anti-patrón:** Usar agrupaciones artificiales (`agrupar_por: idInstrumento`) que colapsen múltiples convocatorias individuales en un solo registro de base de datos.
* **Impacto:** Destruye la visibilidad de los fondos regionales específicos (por ejemplo, reduciendo 76 convocatorias individuales de SERCOTEC a solo 5 grupos principales).

### 2. Confiar en Selectores Estáticos sin Depuración
* **Anti-patrón:** Asumir que los layouts visuales de los sitios del gobierno chileno son permanentes (ej: GORE Biobío).
* **Impacto:** Provoca fallos silenciosos o excepciones de extracción (`ExtractionError`). Siempre se debe verificar el HTML renderizado real usando capturas (`screenshot`) y scripts de auditoría en el contenedor.

### 3. Silenciar Fallos del Entorno (Nvidia / CUDA / Playwright)
* **Anti-patrón:** Dejar activos en producción scrapers que dependen de componentes externos pesados (como el scraper LLM con Nvidia API) si el contenedor de Docker no tiene el hardware o las dependencias estables.
* **Impacto:** Genera caídas fatales a nivel de sistema operativo (*Segmentation Fault* / Exit Code 139), deteniendo todo el lote de monitoreo. Deben desactivarse temporalmente (`activa: false` en BD) hasta solucionar la infraestructura.

---

## 📂 Archivos Clave para Referencia
* **Configuración del CLI:** [src/infra/cli.py](file:///home/manager/Sync/python_proyects/grant_pulse/src/infra/cli.py) (Contiene la separación de `sync_single_source_config` y `run_single_source`).
* **Catálogo de Fuentes:** [src/infra/sources/catalog.py](file:///home/manager/Sync/python_proyects/grant_pulse/src/infra/sources/catalog.py) (Define las propiedades duras que sobrescriben los YAML).
* **Reglas de Ejemplo FIA:** [rules/fia.yaml](file:///home/manager/Sync/python_proyects/grant_pulse/rules/fia.yaml) (Alineada con `per_page=100`).
* **Reglas de Ejemplo SERCOTEC:** [rules/sercotec.yaml](file:///home/manager/Sync/python_proyects/grant_pulse/rules/sercotec.yaml) (Ejemplo de API sin agrupación artificial y con parámetros de gran volumen).
