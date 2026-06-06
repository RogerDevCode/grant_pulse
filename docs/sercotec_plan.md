# Plan: Carga completa de postulaciones SERCOTEC

**Fecha:** 2026-06-06  
**Estado:** En ejecución

---

## 1. Diagnóstico del Problema

### Síntoma
La aplicación muestra solo 2 postulaciones de SERCOTEC cuando el sitio real muestra muchas más.

### Causa Raíz (Confirmada por ingeniería inversa)

La página `https://www.sercotec.cl/postulaciones-abiertas/` **no contiene datos en el HTML**.
Los datos se cargan desde un **iframe** que apunta a una app Next.js:

```
<iframe src="https://sctwebwidgets.sercotec.cl/convocatorias" ...>
```

Esa app a su vez llama a una **API REST** con parámetros:

```
GET https://apisctwidgets.sercotec.cl/api/convocatorias?idRegion=0&idTipoInstrumento=0&idEtapa=0&pagina=1&cantidad=8
```

### Los 3 bugs encontrados

| # | Bug | Efecto |
|---|-----|--------|
| 1 | URL sin params retorna 8 items (default backend) | Solo 8 de 76 postulaciones |
| 2 | `agrupar_por: idInstrumento` colapsa 76 filas a 5 únicos | Se muestran solo 5 |
| 3 | Bug en lógica de agrupación: solo guarda primer item | Se muestran solo 2 |

### Evidencia

```bash
# URL actual (sin params) -> 8 items
curl "https://apisctwidgets.sercotec.cl/api/convocatorias"

# URL correcta con cantidad=200 -> 76 items
curl "https://apisctwidgets.sercotec.cl/api/convocatorias?idRegion=0&idTipoInstrumento=0&idEtapa=0&pagina=1&cantidad=200"
```

**Endpoints adicionales descubiertos:**
- `GET https://apisctwidgets.sercotec.cl/api/regiones` — 16 regiones
- `GET https://apisctwidgets.sercotec.cl/api/categorias` — 3 categorias  
- `GET https://apisctwidgets.sercotec.cl/api/convocatoria?codBP={id}` — detalle por codBp

---

## 2. Estrategia de Corrección

### Decisión de diseño: NO agrupar por instrumento

**Motivo:** Cada `codBp` es una convocatoria-región independiente. Una persona en Tarapacá
quiere ver la convocatoria de Tarapacá, no un registro genérico "disponible en N regiones".
La granularidad por codBp es la correcta para el sistema de monitoreo.

Si en el futuro se quiere agrupar para deduplicar alertas, se hace a nivel de notificación,
no a nivel de extracción de datos.

### Plan de implementación (5 pasos)

#### Paso 1: Actualizar URL en catalog.py y sercotec.yaml
- Agregar `?idRegion=0&idTipoInstrumento=0&idEtapa=0&pagina=1&cantidad=500` a la URL
- Eliminar `agrupar_por` del YAML

#### Paso 2: Implementar paginación sercotec-nativa en json_api.py
- La API soporta `pagina` y `cantidad`
- Si la API retorna menos items que `cantidad`, no hay mas páginas
- Implementar loop de paginación para cuando haya mas de 500 items

#### Paso 3: Corregir lógica de agrupación en json_api.py
- Para SERCOTEC: quitar agrupación completamente — cada `codBp` = 1 convocatoria
- El bug actual solo guardaba el primer item de cada grupo idInstrumento

#### Paso 4: Tests de verificación
- Test unitario: mock API retorna 76 items -> extractor retorna 76 registros
- Test integración: pipeline procesa y persiste todas las convocatorias
- Smoke test: contar convocatorias SERCOTEC en BD mayor a 10

---

## 3. Cambios de Archivos

| Archivo | Acción | Motivo |
|---------|--------|--------|
| `rules/sercotec.yaml` | Modificar URL + quitar agrupar_por | Fix principal |
| `src/infra/sources/catalog.py` | Actualizar URL en _SERCOTEC | Sync con YAML |
| `src/infra/scraping/json_api.py` | Paginación nativa pagina+cantidad | Completitud |
| `tests/test_sercotec_scraper.py` | Nuevo archivo de tests | Validación |

---

## 4. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Mitigación |
|--------|-------------|------------|
| API cambia URL sin avisar | Media | Alertas de ScrapingError a Telegram |
| Mas de 500 items futuros | Baja | Paginación implementada |
| Rate limiting por cantidad=500 | Baja | User-Agent realista + retry |

---

## 5. Checklist de Validación

- [ ] curl retorna >= 70 items con cantidad=500
- [ ] json_api.py extrae 76 records sin agrupar
- [ ] BD contiene >= 70 convocatorias SERCOTEC
- [ ] Tests pasan: pytest tests/test_sercotec_scraper.py -v
- [ ] ruff check y mypy pasan limpio

---

## 6. Estado de Ejecución

| Paso | Estado |
|------|--------|
| Diagnóstico | COMPLETO |
| Paso 1: URL + YAML | EN PROGRESO |
| Paso 2: Paginación | EN PROGRESO |
| Paso 3: Fix agrupación | EN PROGRESO |
| Paso 4: Tests | PENDIENTE |
| Validación BD | PENDIENTE |

---

## 7. Resultados de Validación

### Tests
- **11/11 tests nuevos pasan** (tests/unit/test_sercotec_scraper.py)
- **286/286 tests totales pasan** (cero regresiones)
- Ruff: All checks passed
- Mypy: Success: no issues found

### Verificación en vivo (API real)
```
Total convocatorias extraidas: 76
IDs unicos: 76
```

vs antes: **2 postulaciones mostradas**

### Causa raíz confirmada
1. URL `?pagina=1&cantidad=500` → 76 items vs 8 sin params
2. `agrupar_por: idInstrumento` eliminado → 76 items vs 5 agrupados
3. Bug de lógica de agrupación → también colapsaba erróneamente
