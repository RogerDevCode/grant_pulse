# GrantPulse

**GrantPulse** es un sistema inteligente y resiliente diseñado para monitorear aperturas y cambios en convocatorias de financiamiento de instituciones públicas chilenas (CORFO, ANID, SERCOTEC, INDAP, etc.).

El sistema automatiza la recolección de datos, detecta cambios relevantes (nuevas fechas de cierre, cambios de monto o estado) y notifica instantáneamente de forma multicanal.

---

## Características Principales

- **Scraping Hibrido**:
  - **Estatico**: Extraccion rapida via CSS selectors.
  - **API JSON**: Conexion directa a endpoints internos.
  - **Browser (Playwright)**: Navegador real para bypass de protecciones y renderizado de JavaScript.
  - **IA (LLM)**: Extraccion inteligente via OpenRouter (NVIDIA Nemotron/Llama) y **Descubrimiento Dinamico de URLs** desde la Home.
- **Deteccion de Cambios**: Motor de reglas que identifica modificaciones sensibles diferenciandolas de cambios decorativos.
- **Notificaciones Dinamicas**: Gestion de multiples canales de **Telegram** y **Email (SMTP)** directamente desde la interfaz web.
- **Arquitectura Robusta**: Python 3.13, PostgreSQL 17, asincronia completa y validacion estricta (Mypy/Pyright).

---

## Configuracion de Reglas (YAML)

Crea archivos en la carpeta `rules/` para cada organismo.

```yaml
nombre: "Institucion Ejemplo"
url_busqueda: "https://www.institucion.cl/fondos"
estrategia: "browser" # html_static, json_api, browser, llm

# Selectores (para html_static o browser)
selectores:
  contenedor_items: "div.card"
  identificador: "h3.title"
  titulo: "h3.title"
  estado: "span.badge"
  fecha_cierre: ".cierre-date"

# Mapeo JSON (solo para estrategia json_api)
json_mapping:
  root_path: "data.items"
  identificador: "id"
  titulo: "name"

# IA (opcional)
# Si estrategia es 'llm' y url_busqueda es la home, la IA buscara el link de fondos.
```

---

## Uso de la Aplicacion

### 0. Validacion reproducible

Todos los comandos de calidad usan el venv del proyecto (no requieren activacion manual):

```bash
make lint          # ruff check
make format        # ruff format
make typecheck     # mypy + pyright
make test          # pytest
make validate      # lint + typecheck + test
```

### 1. Gestion de Infraestructura
Levanta el sistema completo (DB + API + Worker):
```bash
make up
```
*El sistema buscara automaticamente puertos libres (incrementos de +3) para evitar colisiones.*

### 2. Sincronizacion Masiva (Recomendado)
Para cargar todos los organismos definidos en `rules/` y ejecutar su monitoreo inicial:
```bash
./sync_all.sh
```

### 3. Ejecucion Manual
Para probar una regla especifica:
```bash
docker compose exec api python -m src.infra.cli run-file rules/mi_regla.yaml
```

### 4. Interfaz Web
Accede a `http://localhost:8000` (o el puerto notificado por el sistema):
- **Dashboard**: Visualiza convocatorias activas y el historial de cambios detallado.
- **Configuracion**: Administra tus tokens de Telegram y servidores de Email en tiempo real.

---

## Mantenimiento
- **Ver logs**: `make logs`
- **Limpiar datos**: `make clean` (Borra monitoreos pero **conserva** tus configuraciones de Telegram/Email).
- **Actualizar tablas**: `make migrate`

---

## Requisitos
- Docker y Docker Compose.
- Puerto 8000 y 5432 disponibles (o el sistema asignara alternativos).
- Python 3.13+ con venv en `./venv/`.
