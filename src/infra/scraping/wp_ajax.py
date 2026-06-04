"""
Motor de scraping para endpoints WordPress admin-ajax.php.

Funciona en dos fases:
1. fetch(): Hace GET a la página principal para extraer el nonce dinámico,
   luego POST a admin-ajax.php con el action y nonce. Itera páginas.
2. extract(): Parsea la respuesta JSON {"found": N, "html": "..."}
   y extrae items del HTML embebido usando selectolax.
"""

import hashlib
import json
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

_NONCE_PATTERN = re.compile(r'"nonce"\s*:\s*"([^"]+)"')
_AJAXURL_PATTERN = re.compile(r'"ajaxurl"\s*:\s*"([^"]+)"')
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
}


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


class WpAjaxScraper(ScraperPort):
    """
    Adaptador que extrae convocatorias vía WordPress admin-ajax.php.

    Requiere que la fuente tenga en configuracion_reglas:
    - url_busqueda: la página principal que contiene el nonce
    - selectores: para extraer items del HTML embebido en la respuesta AJAX
    """

    def __init__(self, timeout: int = 20, max_pages: int = 12) -> None:
        self._timeout = timeout
        self._max_pages = max_pages

    async def _resolve_nonce_and_ajax_url(self, page_url: str) -> tuple[str, str]:
        """Obtiene el nonce y la URL de admin-ajax.php desde la página principal."""
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, headers=_BROWSER_HEADERS, follow_redirects=True
            ) as client:
                response = await client.get(page_url)
                response.raise_for_status()
                html = response.text
        except httpx.HTTPStatusError as e:
            msg = f"Error HTTP {e.response.status_code} al obtener nonce desde {page_url}"
            raise NetworkError(msg) from e
        except httpx.RequestError as e:
            msg = f"Error de red al obtener nonce desde {page_url}: {e}"
            raise NetworkError(msg) from e

        nonce_match = _NONCE_PATTERN.search(html)
        ajaxurl_match = _AJAXURL_PATTERN.search(html)

        if not nonce_match:
            raise ExtractionError(f"No se encontró nonce en {page_url}")

        nonce = nonce_match.group(1)
        ajax_url = ajaxurl_match.group(1).replace("\\/", "/") if ajaxurl_match else ""

        if not ajax_url:
            ajax_url = urljoin(page_url, "/wp-admin/admin-ajax.php")

        logger.info(
            "Nonce y AJAX URL resueltos",
            nonce=nonce[:8] + "...",
            ajax_url=ajax_url,
            page_url=page_url,
        )

        return nonce, ajax_url

    async def fetch(self, fuente: Fuente) -> Snapshot:
        page_url = str(fuente.configuracion_reglas.url_busqueda)
        logger.info("WpAjaxScraper: iniciando fetch", url=page_url, fuente=fuente.nombre)

        nonce, ajax_url = await self._resolve_nonce_and_ajax_url(page_url)

        ajax_action_name = "filter_convocatorias"
        post_type = "convocatoria"

        all_html_parts: list[str] = []
        total_found = 0
        pages_fetched = 0

        async with httpx.AsyncClient(
            timeout=self._timeout, headers=_BROWSER_HEADERS, follow_redirects=True
        ) as client:
            for page_num in range(1, self._max_pages + 1):
                form_data = {
                    "action": ajax_action_name,
                    "page": str(page_num),
                    "post_type": post_type,
                    "nonce": nonce,
                }

                headers = {
                    **_BROWSER_HEADERS,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": page_url,
                    "Origin": page_url.rstrip("/").rsplit("/", 1)[0] if "/" in page_url else page_url,
                }

                try:
                    response = await client.post(ajax_url, data=form_data, headers=headers)
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    if page_num == 1:
                        msg = f"Error HTTP {e.response.status_code} en AJAX POST a {ajax_url}"
                        raise NetworkError(msg) from e
                    logger.warning(
                        "Error en página de AJAX, deteniendo paginación",
                        page=page_num,
                        status=e.response.status_code,
                    )
                    break
                except httpx.RequestError as e:
                    if page_num == 1:
                        msg = f"Error de red en AJAX POST a {ajax_url}: {e}"
                        raise NetworkError(msg) from e
                    logger.warning("Error de red en paginación AJAX", page=page_num, exc=e)
                    break

                try:
                    data = response.json()
                except json.JSONDecodeError as e:
                    if page_num == 1:
                        msg = f"Respuesta AJAX no es JSON válido: {response.text[:200]}"
                        raise ExtractionError(msg) from e
                    logger.warning("Respuesta no-JSON en paginación", page=page_num)
                    break

                html_part = data.get("html", "")
                found = data.get("found", 0)

                if page_num == 1:
                    total_found = found
                    logger.info(
                        "AJAX respondió con datos",
                        found=found,
                        html_length=len(html_part),
                        fuente=fuente.nombre,
                    )

                if not html_part:
                    logger.info("Página vacía, fin de paginación", page=page_num)
                    break

                all_html_parts.append(html_part)
                pages_fetched = page_num

                if total_found > 0 and page_num * 10 >= total_found:
                    break

        combined_html = "\n".join(all_html_parts)
        content_hash = hashlib.sha256(combined_html.encode("utf-8")).hexdigest()

        metadata = {
            "scraper_type": "wp_ajax",
            "ajax_url": ajax_url,
            "total_found": total_found,
            "pages_fetched": pages_fetched,
        }
        combined_content = json.dumps({"metadata": metadata, "html": combined_html})

        return Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=combined_content,
            hash_contenido=content_hash,
            estado_ejecucion="SUCCESS",
        )

    async def extract(self, snapshot: Snapshot, fuente: Fuente, **_kwargs: Any) -> list[dict[str, str | None]]:
        logger.info("WpAjaxScraper: iniciando extracción", fuente=fuente.nombre)

        try:
            wrapper = json.loads(snapshot.contenido_crudo)
            html_content = wrapper.get("html", snapshot.contenido_crudo)
        except json.JSONDecodeError:
            html_content = snapshot.contenido_crudo

        try:
            tree = HTMLParser(html_content)
        except Exception as e:
            msg = f"Fallo parseando HTML del AJAX response para {fuente.nombre}"
            logger.error(msg, exc=e)
            raise ExtractionError(msg) from e

        selectores = fuente.configuracion_reglas.selectores
        if not selectores:
            raise ExtractionError(f"No se han configurado selectores para la fuente {fuente.nombre}")

        contenedor_selector = selectores.contenedor_items
        items_nodos = tree.css(contenedor_selector)

        if not items_nodos:
            logger.warning(
                "No se encontraron items con el selector AJAX",
                selector=contenedor_selector,
                fuente=fuente.nombre,
            )
            return []

        resultados: list[dict[str, str | None]] = []

        for index, nodo in enumerate(items_nodos):
            try:
                item_data: dict[str, str | None] = {}

                titulo_nodo = _resolve_node(nodo, selectores.titulo)
                titulo_text = _extract_text_or_attr(titulo_nodo, selectores.titulo)
                item_data["titulo"] = titulo_text

                identificador_nodo = _resolve_node(nodo, selectores.identificador)
                identificador_raw = _extract_text_or_attr(identificador_nodo, selectores.identificador)
                if not identificador_raw and titulo_text:
                    identificador_raw = "hash-" + hashlib.md5(titulo_text.encode("utf-8")).hexdigest()[:10]
                item_data["identificador"] = identificador_raw

                if not item_data["identificador"] or not item_data["titulo"]:
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
                    item_data["fecha_cierre"] = raw_fc
                else:
                    item_data["fecha_cierre"] = None

                if selectores.monto:
                    monto_nodo = _resolve_node(nodo, selectores.monto)
                    item_data["monto"] = _extract_text_or_attr(monto_nodo, selectores.monto)
                else:
                    item_data["monto"] = None

                resultados.append(item_data)
            except Exception as e:
                logger.warning(f"Error parcial extrayendo item AJAX #{index}: {e}")
                continue

        if not resultados and items_nodos:
            msg = f"Se encontraron contenedores AJAX pero ningún item pudo ser extraído para {fuente.nombre}"
            raise ExtractionError(msg)

        logger.info(
            "WpAjaxScraper: extracción completada",
            items=len(resultados),
            fuente=fuente.nombre,
        )

        return resultados
