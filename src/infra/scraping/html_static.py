"""
Implementación del motor de scraping estático basado en httpx y selectolax.
"""

import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import httpx
from selectolax.parser import HTMLParser

from src.core.domain.entities import Fuente, Snapshot
from src.core.domain.estado_normalizer import normalize_estado
from src.core.domain.exceptions import ExtractionError, NetworkError
from src.core.domain.ports import ScraperPort
from src.infra.logging import get_logger

logger = get_logger(__name__)


def _resolve_node(root: Any, selector: str) -> Any | None:
    if selector == "self":
        return root
    if selector.startswith("attr:"):
        return root
    return root.css_first(selector)


def _extract_text_or_attr(root: Any | None, selector: str) -> str | None:
    if root is None:
        return None
    if selector.startswith("attr:"):
        attr_name = selector.split(":", 1)[1]
        attr_val = root.attributes.get(attr_name)
        if isinstance(attr_val, str):
            value = attr_val.strip()
            return value or None
        return None
    value = root.text(strip=True).strip()
    return value or None


def _apply_normalizer(raw_text: str | None, field_name: str, fuente: Fuente) -> str | None:
    if not raw_text:
        return None
    norm_cfg = getattr(fuente.configuracion_reglas.normalizadores, field_name, None)
    if not norm_cfg or not norm_cfg.regex_extraction:
        return raw_text
    match = re.search(norm_cfg.regex_extraction, raw_text)
    return match.group(1).strip() if match else raw_text


class HtmlStaticScraper(ScraperPort):
    """
    Adaptador de scraping que realiza peticiones GET simples y
    parsea el HTML estático resultante de forma eficiente.
    """

    def __init__(self, timeout: int = 15) -> None:
        self._timeout = timeout

    async def fetch(self, fuente: Fuente) -> Snapshot:
        url = str(fuente.url_base)
        if fuente.configuracion_reglas.url_busqueda:
            url = str(fuente.configuracion_reglas.url_busqueda)

        logger.info("Realizando fetch", url=url, fuente_id=str(fuente.id))

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout, headers=headers, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                html_content = response.text
        except httpx.HTTPStatusError as e:
            msg = f"Error HTTP {e.response.status_code} al acceder a {url}"
            logger.error(msg, exc=e)
            raise NetworkError(msg) from e
        except httpx.RequestError as e:
            msg = f"Error de red al acceder a {url}: {e}"
            logger.error(msg, exc=e)
            raise NetworkError(msg) from e

        content_hash = hashlib.sha256(html_content.encode("utf-8")).hexdigest()

        snapshot = Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=html_content,
            hash_contenido=content_hash,
            estado_ejecucion="SUCCESS",
        )
        return snapshot

    async def extract(self, snapshot: Snapshot, fuente: Fuente, **kwargs: Any) -> list[dict[str, str | None]]:  # noqa: ARG002
        logger.info("Iniciando extracción", snapshot_id=str(snapshot.id), fuente_id=str(fuente.id))

        try:
            tree = HTMLParser(snapshot.contenido_crudo)
        except Exception as e:
            msg = f"Fallo catastrófico parseando HTML crudo en snapshot {snapshot.id}"
            logger.error(msg, exc=e)
            raise ExtractionError(msg) from e

        selectores = fuente.configuracion_reglas.selectores
        if not selectores:
            raise ExtractionError(f"No se han configurado selectores para la fuente {fuente.nombre}")

        contenedor_selector = selectores.contenedor_items

        items_nodos = tree.css(contenedor_selector)
        if not items_nodos:
            logger.warning(
                "No se encontraron items con el selector provisto",
                selector=contenedor_selector,
                fuente_id=str(fuente.id),
            )
            return []

        resultados: list[dict[str, str | None]] = []

        for index, nodo in enumerate(items_nodos):
            try:
                item_data: dict[str, str | None] = {}

                titulo_nodo = _resolve_node(nodo, selectores.titulo)
                titulo_text = _extract_text_or_attr(titulo_nodo, selectores.titulo)
                titulo_text = _apply_normalizer(titulo_text, "titulo", fuente) or titulo_text
                item_data["titulo"] = titulo_text

                identificador_nodo = _resolve_node(nodo, selectores.identificador)
                identificador_raw = _extract_text_or_attr(identificador_nodo, selectores.identificador)
                if identificador_raw and selectores.identificador == selectores.titulo:
                    identificador_raw = _apply_normalizer(identificador_raw, "titulo", fuente) or identificador_raw

                if not identificador_raw and titulo_text:
                    identificador_raw = "hash-" + hashlib.md5(titulo_text.encode("utf-8")).hexdigest()[:10]

                item_data["identificador"] = identificador_raw

                if not item_data["identificador"]:
                    logger.debug(f"Item #{index} no tiene identificador ni título para fallback. Saltando.")
                    continue

                if not item_data["titulo"]:
                    logger.debug(f"Item #{index} no tiene título. Saltando.")
                    continue

                if selectores.descripcion:
                    desc_nodo = _resolve_node(nodo, selectores.descripcion)
                    item_data["descripcion"] = _extract_text_or_attr(desc_nodo, selectores.descripcion)
                else:
                    item_data["descripcion"] = None

                link_nodo = None
                if selectores.link_detalle:
                    link_nodo = _resolve_node(nodo, selectores.link_detalle)
                if not link_nodo and nodo.tag == "a":
                    link_nodo = nodo
                href_val = link_nodo.attributes.get("href") if link_nodo else None
                if isinstance(href_val, str) and href_val.strip():
                    item_data["url_detalle"] = urljoin(str(fuente.url_base), href_val.strip())
                else:
                    item_data["url_detalle"] = None

                if selectores.estado:
                    estado_nodo = _resolve_node(nodo, selectores.estado)
                    estado_text = _extract_text_or_attr(estado_nodo, selectores.estado)
                    item_data["estado"] = normalize_estado(estado_text)
                else:
                    item_data["estado"] = "DESCONOCIDO"

                if selectores.fecha_cierre:
                    fc_nodo = _resolve_node(nodo, selectores.fecha_cierre)
                    raw_fc = _extract_text_or_attr(fc_nodo, selectores.fecha_cierre)
                    item_data["fecha_cierre"] = _apply_normalizer(raw_fc, "fecha_cierre", fuente)
                else:
                    item_data["fecha_cierre"] = None

                if selectores.monto:
                    monto_nodo = _resolve_node(nodo, selectores.monto)
                    raw_monto = _extract_text_or_attr(monto_nodo, selectores.monto)
                    item_data["monto"] = _apply_normalizer(raw_monto, "monto", fuente)
                else:
                    item_data["monto"] = None

                if selectores.region:
                    region_nodo = _resolve_node(nodo, selectores.region)
                    raw_region = _extract_text_or_attr(region_nodo, selectores.region)
                    item_data["region"] = _apply_normalizer(raw_region, "region", fuente)
                else:
                    item_data["region"] = None

                resultados.append(item_data)

            except Exception as e:
                logger.warning(f"Error parcial extrayendo item #{index}: {e}")
                continue

        if not resultados and items_nodos:
            msg = "Se encontraron contenedores pero ningún item pudo ser extraído."
            logger.error(msg, fuente_id=str(fuente.id))
            raise ExtractionError(msg)

        return resultados
