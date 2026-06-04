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

    Soporta paginación automática cuando PaginationConfig tiene
    total_pages_header configurado (ej: WordPress REST API).
    """

    def __init__(self, timeout: int = 20) -> None:
        self._timeout = timeout

    async def fetch(self, fuente: Fuente) -> Snapshot:
        url = str(fuente.configuracion_reglas.url_busqueda)
        mapping = fuente.configuracion_reglas.json_mapping
        pagination = mapping.paginacion if mapping else None
        has_pagination = pagination and pagination.total_pages_header

        logger.info(
            "Realizando fetch JSON API",
            url=url,
            fuente_id=str(fuente.id),
            paginacion=has_pagination is not None,
        )

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout, headers=headers, follow_redirects=True) as client:
                if not has_pagination:
                    response = await client.get(url)
                    response.raise_for_status()
                    json_content = response.text
                else:
                    json_content = await self._fetch_all_pages(client, url, pagination)
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
        """Itera todas las páginas de una API paginada y consolida los items."""
        all_items: list[Any] = []
        page = 1
        total_pages: int | None = None

        while True:
            page_url = _set_query_param(base_url, pagination.page_param, str(page))
            logger.info("Fetch página", page=page, url=page_url)

            response = await client.get(page_url)
            response.raise_for_status()

            page_data = response.json()
            if not isinstance(page_data, list):
                page_data = [page_data]

            all_items.extend(page_data)
            logger.info(
                "Página recibida",
                page=page,
                items_en_pagina=len(page_data),
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

            if len(page_data) == 0:
                logger.info("Página vacía recibida, deteniendo paginación", page=page)
                break

        logger.info("Paginación completada", total_items=len(all_items), paginas=page)
        return json.dumps(all_items)

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
                    "fecha_cierre": _coerce_text(get_by_path(raw_item, mapping.fecha_cierre))
                    if mapping.fecha_cierre
                    else None,
                    "monto": _coerce_text(get_by_path(raw_item, mapping.monto)) if mapping.monto else None,
                }

                if not item_data["identificador"]:
                    raise ValueError(f"Falta identificador en path JSON '{mapping.identificador}'")
                if not item_data["titulo"]:
                    raise ValueError(f"Falta titulo en path JSON '{mapping.titulo}'")

                resultados.append(item_data)
            except Exception as e:
                logger.error(f"Error extrayendo item JSON #{index}: {e}", exc=e)
                # Fail-fast si la estructura del JSON cambió radicalmente
                raise ExtractionError(f"Error en estructura JSON item #{index}") from e

        return resultados
