"""
Implementación del motor de scraping para APIs JSON con soporte de paginación.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx

from src.core.domain.entities import Fuente, Snapshot
from src.core.domain.estado_normalizer import normalize_estado
from src.core.domain.exceptions import ExtractionError, NetworkError
from src.core.domain.ports import ScraperPort
from src.infra.logging import get_logger

logger = get_logger(__name__)


def get_by_path(data: Any, path: str | None) -> Any:
    """Navega un objeto JSON usando una ruta de puntos (ej: 'data.items.0.id')."""
    if not path:
        return data

    parts = path.split(".")
    current: Any = data
    for part in parts:
        try:
            if isinstance(current, list):
                current = current[int(part)]  # pyright: ignore[reportUnknownVariableType]
            elif isinstance(current, dict):
                current = current.get(part)  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            else:
                return None
        except (AttributeError, KeyError, IndexError, ValueError):
            return None
        if current is None:
            break
    return current  # pyright: ignore[reportUnknownVariableType]


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _set_query_param(url: str, param: str, value: str) -> str:
    """Agrega o reemplaza un query param en una URL."""
    parts = urlsplit(url)
    query = parse_qs(parts.query, keep_blank_values=True)
    query[param] = [value]
    new_query = urlencode(query, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


class JsonApiScraper(ScraperPort):
    """
    Adaptador de scraping que consume un endpoint JSON y extrae
    los campos mapeando llaves de la respuesta.

    Soporta dos estrategias de paginación:
    1. Header-based (ej: WordPress REST API): usa total_pages_header en PaginationConfig.
    2. Param-based (ej: SERCOTEC API): detecta param 'pagina' en la URL y agrega páginas
       sucesivas mientras la respuesta retorne exactamente 'cantidad' items.
    """

    def __init__(self, timeout: int = 20) -> None:
        self._timeout = timeout

    def _detect_param_pagination(self, url: str) -> tuple[str, int] | None:
        """Detecta si la URL usa paginación por param 'pagina'+'cantidad'.

        Retorna (base_url, cantidad_por_pagina) si aplica, None si no.
        Esto ocurre cuando la URL tiene explicitamente 'pagina=' y 'cantidad='.
        """
        params = parse_qs(urlsplit(url).query, keep_blank_values=True)
        if "pagina" in params and "cantidad" in params:
            try:
                cantidad = int(params["cantidad"][0])
                return url, cantidad
            except (ValueError, IndexError):
                pass
        return None

    async def fetch(self, fuente: Fuente) -> Snapshot:
        url = str(fuente.configuracion_reglas.url_busqueda)
        mapping = fuente.configuracion_reglas.json_mapping
        pagination = mapping.paginacion if mapping else None
        has_header_pagination = pagination and pagination.total_pages_header
        param_pagination = self._detect_param_pagination(url)

        logger.info(
            "Realizando fetch JSON API",
            url=url,
            fuente_id=str(fuente.id),
            paginacion_header=has_header_pagination is not None,
            paginacion_param=param_pagination is not None,
        )

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout, headers=headers, follow_redirects=True) as client:
                if has_header_pagination:
                    json_content = await self._fetch_all_pages(client, url, pagination)
                elif param_pagination:
                    base_url, cantidad = param_pagination
                    json_content = await self._fetch_param_pages(client, base_url, cantidad, mapping)
                else:
                    response = await client.get(url)
                    response.raise_for_status()
                    json_content = response.text
        except httpx.HTTPStatusError as e:
            msg = f"Error HTTP {e.response.status_code} al acceder a API {url}"
            logger.error(msg, exc=e)
            raise NetworkError(msg) from e
        except httpx.RequestError as e:
            msg = f"Error de red al acceder a API {url}: {e}"
            logger.error(msg, exc=e)
            raise NetworkError(msg) from e

        content_hash = hashlib.sha256(json_content.encode("utf-8")).hexdigest()

        return Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=json_content,
            hash_contenido=content_hash,
            estado_ejecucion="SUCCESS",
        )

    async def _fetch_all_pages(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        pagination: Any,
    ) -> str:
        """Itera todas las páginas de una API paginada vía header (ej: WordPress)."""
        all_items: list[Any] = []
        page = 1
        total_pages: int | None = None

        while True:
            page_url = _set_query_param(base_url, pagination.page_param, str(page))
            logger.info("Fetch página (header-pagination)", page=page, url=page_url)

            response = await client.get(page_url)
            response.raise_for_status()

            page_data = response.json()
            if not isinstance(page_data, list):
                page_data = [page_data]

            all_items.extend(page_data)  # pyright: ignore[reportUnknownArgumentType]
            logger.info(
                "Página recibida",
                page=page,
                items_en_pagina=len(page_data),  # pyright: ignore[reportUnknownArgumentType]
                total_acumulado=len(all_items),
            )

            if total_pages is None:
                total_pages_str = response.headers.get(pagination.total_pages_header)
                if total_pages_str:
                    total_pages = int(total_pages_str)
                    total_items_str = (
                        response.headers.get(pagination.total_items_header)
                        if pagination.total_items_header
                        else "?"
                    )
                    logger.info(
                        "Paginación detectada",
                        total_pages=total_pages,
                        total_items=total_items_str,
                    )
                else:
                    logger.warning(
                        "Header de total_pages no encontrado, asumiendo 1 página",
                        header=pagination.total_pages_header,
                    )
                    total_pages = 1

            if page >= total_pages:
                break

            page += 1

            if page > pagination.max_pages:
                logger.warning(
                    "Límite de páginas alcanzado, deteniendo paginación",
                    max_pages=pagination.max_pages,
                    total_pages=total_pages,
                )
                break

            if len(page_data) == 0:  # pyright: ignore[reportUnknownArgumentType]
                logger.info("Página vacía recibida, deteniendo paginación", page=page)
                break

        logger.info("Paginación header completada", total_items=len(all_items), paginas=page)
        return json.dumps(all_items)

    async def _fetch_param_pages(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        cantidad_por_pagina: int,
        mapping: Any,
    ) -> str:
        """Paginación nativa por parámetro 'pagina' (ej: SERCOTEC API).

        Algoritmo:
        - La URL ya tiene pagina=1 y cantidad=N.
        - Se parsean los items de la primera página.
        - Si len(items_pagina) == cantidad_por_pagina, puede haber más páginas.
        - Se reemplaza pagina=1 por pagina=2, etc. hasta que items < cantidad.
        - Consolidar items usando root_path para extraer la lista del JSON.
        """
        all_items: list[Any] = []
        page = 1
        max_pages = 50  # Salvaguarda: máximo 50 páginas * 500 items = 25.000 convocatorias

        while page <= max_pages:
            # Reemplazar el param 'pagina' con la página actual
            parts = urlsplit(base_url)
            params = parse_qs(parts.query, keep_blank_values=True)
            params["pagina"] = [str(page)]
            new_query = urlencode(params, doseq=True)
            page_url = urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))

            logger.info("Fetch página (param-pagination)", page=page, url=page_url)

            response = await client.get(page_url)
            response.raise_for_status()

            raw = response.json()

            # Extraer la lista de items usando root_path si está configurado
            root_path = mapping.root_path if mapping and mapping.root_path else None
            page_items: list[Any] = get_by_path(raw, root_path) if root_path else raw

            if not isinstance(page_items, list):
                logger.warning(
                    "root_path no devolvió lista en paginación param",
                    page=page,
                    root_path=root_path,
                )
                break

            n_items = len(page_items)
            all_items.extend(page_items)

            logger.info(
                "Página param recibida",
                page=page,
                items_en_pagina=n_items,
                total_acumulado=len(all_items),
            )

            # Si la página tiene menos items que cantidad, es la última página
            if n_items < cantidad_por_pagina:
                logger.info(
                    "Última página detectada (items < cantidad)",
                    page=page,
                    items=n_items,
                    cantidad_max=cantidad_por_pagina,
                )
                break

            page += 1

        logger.info("Paginación param completada", total_items=len(all_items), paginas=page)

        # Reconstruir el JSON con la misma estructura esperada (usando root_path)
        if mapping and mapping.root_path:
            # Envolver en la estructura {root_path: [items]}
            # Para SERCOTEC: {"datos": [...]}
            result = {mapping.root_path: all_items}
        else:
            result = all_items  # type: ignore[assignment]

        return json.dumps(result, ensure_ascii=False)

    async def extract(self, snapshot: Snapshot, fuente: Fuente, **kwargs: Any) -> list[dict[str, str | None]]:  # noqa: ARG002
        logger.info("Extrayendo desde JSON", snapshot_id=str(snapshot.id), fuente_id=str(fuente.id))

        try:
            data = json.loads(snapshot.contenido_crudo)
        except json.JSONDecodeError as e:
            msg = f"Fallo parseando contenido crudo como JSON en snapshot {snapshot.id}"
            logger.error(msg, exc=e)
            raise ExtractionError(msg) from e

        mapping = fuente.configuracion_reglas.json_mapping
        if not mapping:
            raise ExtractionError(f"No se ha configurado json_mapping para la fuente {fuente.nombre}")

        # Obtener la lista raíz de items
        items = get_by_path(data, mapping.root_path)
        if not isinstance(items, list):
            msg = f"El path raíz JSON '{mapping.root_path}' no devolvió una lista para la fuente {fuente.nombre}"
            logger.error(msg, root_path=mapping.root_path, fuente=fuente.nombre)
            raise ExtractionError(msg)

        resultados: list[dict[str, str | None]] = []

        raw_items: list[Any] = items  # pyright: ignore[reportUnknownVariableType]
        for index, raw_item in enumerate(raw_items):
            try:
                # Extraemos cada campo usando la utilidad de path
                item_data = {
                    "identificador": _coerce_text(get_by_path(raw_item, mapping.identificador)),
                    "titulo": _coerce_text(get_by_path(raw_item, mapping.titulo)),
                    "descripcion": _coerce_text(get_by_path(raw_item, mapping.descripcion))
                    if mapping.descripcion
                    else None,
                    "url_detalle": _coerce_text(get_by_path(raw_item, mapping.link_detalle))
                    if mapping.link_detalle
                    else None,
                    "estado": normalize_estado(_coerce_text(get_by_path(raw_item, mapping.estado))) if mapping.estado else "DESCONOCIDO",
                    # fecha_apertura: campo opcional — presente en SERCOTEC (fechaInicio) y FIA (date)
                    "fecha_apertura": _coerce_text(get_by_path(raw_item, mapping.fecha_apertura))
                    if mapping.fecha_apertura
                    else None,
                    "fecha_cierre": _coerce_text(get_by_path(raw_item, mapping.fecha_cierre))
                    if mapping.fecha_cierre
                    else None,
                    "monto": _coerce_text(get_by_path(raw_item, mapping.monto)) if mapping.monto else None,
                    "region": _coerce_text(get_by_path(raw_item, mapping.region)) if mapping.region else None,
                }

                # Agrupación opcional
                grupo_val = _coerce_text(get_by_path(raw_item, mapping.agrupar_por)) if mapping.agrupar_por else None
                if grupo_val:
                    item_data["_grupo_id"] = grupo_val

                if not item_data["identificador"]:
                    raise ValueError(f"Falta identificador en path JSON '{mapping.identificador}'")
                if not item_data["titulo"]:
                    raise ValueError(f"Falta titulo en path JSON '{mapping.titulo}'")

                resultados.append(item_data)
            except Exception as e:
                logger.error(f"Error extrayendo item JSON #{index}: {e}", exc=e)
                # Fail-fast si la estructura del JSON cambió radicalmente
                raise ExtractionError(f"Error en estructura JSON item #{index}") from e

        if mapping.agrupar_por:
            agrupados: dict[str, dict[str, str | None]] = {}
            for item in resultados:
                gid = item.pop("_grupo_id", None)
                if not gid:
                    # Si no tiene grupo, lo usamos como identificador único
                    agrupados[item["identificador"]] = item  # type: ignore
                    continue

                if gid in agrupados:
                    # Combinar regiones
                    existente = agrupados[gid]
                    if item.get("region") and existente.get("region"):
                        if item["region"] not in existente["region"]:  # type: ignore
                            existente["region"] = f"{existente['region']}, {item['region']}"
                else:
                    item["identificador"] = gid  # El ID agrupador se vuelve el identificador oficial

                    # Normalizar el título eliminando el sufijo regional (ej. " - Región de Aysén")
                    if item["titulo"] and " - Región de " in item["titulo"]:
                        item["titulo"] = item["titulo"].split(" - Región de ")[0].strip()
                    elif item["titulo"] and ", Región de " in item["titulo"]:
                        item["titulo"] = item["titulo"].split(", Región de ")[0].strip()

                    agrupados[gid] = item

            resultados = list(agrupados.values())

        return resultados
