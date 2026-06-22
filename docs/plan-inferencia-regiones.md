# Plan: Inferencia de regiones para convocatorias scrapeadas

## Contexto del bug

El usuario reporta: "Cuando pido que me muestre las convocatorias de CORFO para la región del Biobío, no encuentra alguna. Deberían haber 3 convocatorias".

**Investigación realizada contra producción** (`https://grantpulse-production.up.railway.app`):

1. **Endpoint** `/api/v1/convocatorias?fuente_id=2&region=Biobío` → 0 resultados
2. **Endpoint** `/api/v1/convocatorias?fuente_id=2&limit=200` → 67 items
3. **Distribución de regiones en BD para CORFO**: 67/67 tienen `region=None`
4. **Búsqueda de "Biobío" en título + descripción de los 67 items**: 0 menciones
5. **Heurística por palabras clave** (Arica, Tarapacá, Valparaíso, Ñuble, etc.) detecta 39 de 67 items
6. **Biobío NO aparece en ningún título ni descripción de las 67 convocatorias scrapeadas**

## Causa raíz

El `WpAjaxScraper` (`src/infra/scraping/wp_ajax.py:325`) extrae `region` desde un selector CSS (`h4`), pero el HTML real de CORFO no tiene la región en ese nodo. Resultado: `region=None` para todos los items.

Adicionalmente, `region_defecto: "Nacional"` en `rules/corfo.yaml` no se aplica porque el normalizador lo ignora o el scraper sobrescribe con `None`.

## Por qué la heurística de texto no resuelve Biobío

Aunque la heurística detecta 39/67 items (Arica, Tarapacá, Coquimbo, Valparaíso, Metropolitana, Ñuble, La Araucanía, Los Lagos, Aysén, Magallanes), **no detecta Biobío** porque el sitio no devuelve convocatorias con esa mención textual en este momento.

Verificación adicional:
- Google search de `site:corfo.gob.cl biobío convocatoria 2026` → bloqueado
- `gorebiobio.cl` → vacío (403/cortafuegos)

**No es viable asegurar 3 convocatorias de Biobío si el sitio no las expone al scraper**.

## Estrategia propuesta

En lugar de una heurística textual frágil, inferencia estructurada por **patrones de título** específicos de los Comités de Desarrollo Productivo Regional (CDPR). Los instrumentos CORFO regionales siguen nomenclatura fija:

```
"DESARROLLA INVERSIÓN PRODUCTIVA – REGIÓN DE X – N° CONVOCATORIA 2026"
"RED PROVEEDORES – REGIÓN DE X – ETAPA Y"
"INNOVA REGIÓN – REGIÓN DE X 2026"
"PRIMER CONCURSO INNOVA REGIÓN 2026 REGIÓN DE X"
"VIRALIZA EVENTOS REGIÓN DE X"
```

### Normalizador nuevo: `RegionInferer`

Ubicación: `src/core/application/region_inferrer.py` (nuevo)

```python
"""
Inferencia determinística de regiones a partir del título y descripción
de la convocatoria. Patrones regex específicos por familia de instrumentos.
"""

import re
from typing import List

REGIONES_CANONICAS = [
    "Arica y Parinacota", "Tarapacá", "Antofagasta", "Atacama",
    "Coquimbo", "Valparaíso", "Metropolitana", "O'Higgins", "Maule",
    "Ñuble", "Biobío", "La Araucanía", "Los Ríos", "Los Lagos",
    "Aysén", "Magallanes",
]

# Normalización para matching: minúsculas + sin tildes + sin apostrofes
def _normalizar(s: str) -> str:
    s = s.lower()
    repl = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n", "'": ""}
    for k, v in repl.items():
        s = s.replace(k, v)
    return s

_REGIONES_NORMALIZADAS = {r: _normalizar(r) for r in REGIONES_CANONICAS}

# Patrones ordenados por especificidad (más específico primero)
_PATRONES_REGION = [
    # "REGIÓN DE X" con palabras circundantes típicas de CORFO
    r"region\s+de\s+([a-záéíóúñ\s]+?)(?:\s*[-,–]|\s+\d{4}|\s+conv\.|$)",
    # "REGIÓN X" sin "de" intermedia
    r"region\s+([a-záéíóúñ]+)(?:\s*[-,–]|\s+\d{4}|\s+conv\.|$)",
    # "INNOVA REGIÓN X" sin espacio
    r"innova\s+region\s+([a-záéíóúñ]+)",
    # "SÚMATE A INNOVAR X"
    r"sumate\s+a\s+innovar\s+([a-záéíóúñ]+)",
    # "SEMILLA INICIA AÑO 2026, REGIÓN DE X"
    r"semilla\s+inicia\s+a[ñn]o\s+\d{4},?\s+region\s+de\s+([a-záéíóúñ\s]+?)$",
]

def inferir_regiones(titulo: str, descripcion: str = "") -> List[str]:
    """Devuelve lista de regiones canónicas detectadas. Vacía si no se detecta ninguna."""
    blob = _normalizar(titulo + " " + descripcion)
    regiones_detectadas: set[str] = set()

    for patron in _PATRONES_REGION:
        for match in re.finditer(patron, blob, re.IGNORECASE):
            candidato = match.group(1).strip().rstrip(",.;-–")
            candidato_norm = _normalizar(candidato)
            # Buscar match exacto contra regiones canónicas normalizadas
            for canonica, normalizada in _REGIONES_NORMALIZADAS.items():
                if candidato_norm == normalizada or normalizada in candidato_norm:
                    regiones_detectadas.add(canonica)

    return sorted(regiones_detectadas)
```

### Integración en el pipeline de scraping

`src/infra/maintenance.py:111` ya tiene un lugar para enriquecer con LLM. Insertar antes el `RegionInferer`:

```python
# Antes de invocar LLM, intentar inferencia determinística
from src.core.application.region_inferrer import inferir_regiones

regiones = inferir_regiones(
    convocatoria.titulo,
    convocatoria.descripcion or ""
)
if regiones:
    convocatoria.regiones = regiones
else:
    # Fallback: LLM solo si la heurística falla
    regiones = _infer_region_with_llm(...)
```

### Tests del inferidor

`tests/unit/test_region_inferrer.py`:

```python
from src.core.application.region_inferrer import inferir_regiones

CASOS = [
    # (titulo, descripcion, esperado)
    (
        "Red Tecnológica GTT+",
        "Si tienes interés en participar...",
        [],
    ),
    (
        "DESARROLLA INVERSIÓN PRODUCTIVA – REGIÓN DE ÑUBLE – 1° CONVOCATORIA 2026",
        "",
        ["Ñuble"],
    ),
    (
        "INNOVA REGIÓN – REGIÓN DE TARAPACÁ 2026",
        "",
        ["Tarapacá"],
    ),
    (
        "Súmate a Innovar Los Lagos 2026",
        "",
        ["Los Lagos"],
    ),
    (
        "Viraliza Eventos Región de Valparaíso",
        "",
        ["Valparaíso"],
    ),
    (
        "PRIMER CONCURSO INNOVA REGION 2026 REGION DE ARICA Y PARINACOTA",
        "",
        ["Arica y Parinacota"],
    ),
]
```

### Script de reproceso para BD existente

`scripts/migrations/backfill_regiones.py`:

```python
"""
Reprocesa regiones para convocatorias ya scrapeadas.
Idempotente. Ejecutar después del deploy.
"""
import asyncio
from src.infra.db.connection import AsyncSessionLocal
from src.infra.db.models import ConvocatoriaORM
from src.core.application.region_inferrer import inferir_regiones
from sqlalchemy import select

async def backfill():
    async with AsyncSessionLocal() as session:
        stmt = select(ConvocatoriaORM)
        result = await session.execute(stmt)
        total = 0
        actualizadas = 0
        for orm in result.scalars():
            total += 1
            if not orm.regiones or len(orm.regiones) == 0:
                regiones = inferir_regiones(orm.titulo, orm.descripcion or "")
                if regiones:
                    orm.regiones = regiones
                    actualizadas += 1
        await session.commit()
        print(f"Total procesadas: {total}, con región detectada: {actualizadas}")

if __name__ == "__main__":
    asyncio.run(backfill())
```

## Limitaciones del plan

1. **No garantiza 3 convocatorias para Biobío**. Si el sitio no las expone, no hay forma de inventarlas.
2. **Depende de nomenclatura estable de CORFO**. Si CORFO cambia el formato de los títulos, hay que actualizar patrones.
3. **Falsos negativos posibles**: convocatorias que mencionan regiones en la descripción pero no en el título.
4. **No aplica a otras fuentes** automáticamente. Para FIA, SERCOTEC, etc. hay que validar sus nomenclaturas.

## Resultado esperado

- **Para Biobío**: solo se asignará la región si el título lo menciona explícitamente. Si CORFO no devuelve 3 items con "Biobío" en el título, el conteo será 0 o el real existente.
- **Para otras 16 regiones**: la heurística cubre la mayoría de los casos detectados (39 de 67 en muestra analizada).
- **Trazabilidad**: cada asignación queda en la tabla `convocatorias.regiones` con origen identificable.

## Acciones previas al deploy

1. Ejecutar el script de prueba `python -c "from src.core.application.region_inferrer import inferir_regiones; print(inferir_regiones('PRIMER CONCURSO INNOVA REGION 2026 REGION DE ARICA Y PARINACOTA', ''))"` para validar
2. Correr tests unitarios completos
3. Validar que el endpoint `/convocatorias?fuente_id=2&region=Biobío` devuelva lo correcto

## Riesgos y mitigaciones

- **Riesgo**: cambiar `regiones` de registros activa alertas ya procesadas. **Mitigación**: las alertas se generan por evento (apertura/cambio), no por actualización de regiones. Reproceso no dispara alertas.
- **Riesgo**: asignar región equivocada. **Mitigación**: solo se asigna cuando el match es exacto contra regiones canónicas normalizadas.
- **Riesgo**: si se invoca en cada scrape, podría re-procesar items que ya tienen región. **Mitigación**: el normalizador solo corre si `regiones` está vacía.

## Pendiente del usuario

Antes de ejecutar el plan, confirmar:

1. ¿Tiene usted acceso directo a las 3 convocatorias de CORFO Biobío que espera ver? URLs específicas ayudarían a validar el scraper.
2. ¿Está de acuerdo con que el script asigne regiones solo por heurística de título, sin invocar al sitio?
3. ¿Prefiere aplicar este fix ahora, o espera a tener más datos?
