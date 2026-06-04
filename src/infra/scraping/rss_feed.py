"""
Motor de scraping para feeds RSS/Atom de instituciones chilenas.

Funciona en dos fases:
1. fetch(): Descarga el feed RSS/Atom con headers realistas.
2. extract(): Parsea el XML del feed y mapea items a convocatorias.

Para instituciones como ANID y FIA que publican convocatorias en sus feeds RSS.
"""

import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from src.core.domain.entities import Fuente, Snapshot
from src.core.domain.estado_normalizer import normalize_estado
from src.core.domain.exceptions import ExtractionError, NetworkError
from src.core.domain.ports import ScraperPort
from src.infra.logging import get_logger

logger = get_logger(__name__)

_RSS_NAMESPACES = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "atom": "http://www.w3.org/2005/Atom",
    "wp": "http://wordpress.org/export/1.2/",
}

_ATOM_NS = "http://www.w3.org/2005/Atom"

_CONVOCATORIA_KEYWORDS = re.compile(
    r"\b(convocatoria|concurso|fondo|programa|postulaci[óo]n|licitaci[óo]n|"
    r"financiamiento|subvenci[óo]n|beca|proyecto|emprende|semilla|"
    r"capital|crece|innova|abiert[oa]|vigente|cierre|apertura)\b",
    re.IGNORECASE,
)

_REALISTIC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, application/atom+xml, */*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
}


class RssFeedScraper(ScraperPort):
    """
    Adaptador de scraping que consume feeds RSS/Atom y extrae
    convocatorias de financiamiento desde los items del feed.
    """

    def __init__(self, timeout: int = 20, max_items: int = 50) -> None:
        self._timeout = timeout
        self._max_items = max_items

    async def fetch(self, fuente: Fuente) -> Snapshot:
        url = str(fuente.configuracion_reglas.url_busqueda)
        logger.info("RssFeedScraper: realizando fetch", url=url, fuente=fuente.nombre)

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, headers=_REALISTIC_HEADERS, follow_redirects=True
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                xml_content = response.text
        except httpx.HTTPStatusError as e:
            msg = f"Error HTTP {e.response.status_code} al acceder al feed RSS {url}"
            logger.error(msg, exc=e)
            raise NetworkError(msg) from e
        except httpx.RequestError as e:
            msg = f"Error de red al acceder al feed RSS {url}: {e}"
            logger.error(msg, exc=e)
            raise NetworkError(msg) from e

        content_hash = hashlib.sha256(xml_content.encode("utf-8")).hexdigest()

        return Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=xml_content,
            hash_contenido=content_hash,
            estado_ejecucion="SUCCESS",
        )

    def _detect_status(self, text: str) -> str:
        return normalize_estado(text)

    def _is_convocatoria_relevant(self, title: str, description: str) -> bool:
        """Determina si un item del feed es una convocatoria relevante."""
        combined = f"{title} {description}"
        return bool(_CONVOCATORIA_KEYWORDS.search(combined))

    def _extract_date(self, text: str) -> str | None:
        """Extrae fechas de texto libre en formatos comunes chilenos."""
        patterns = [
            r"(\d{1,2}\s+de\s+\w+\s+de\s+\d{4})",
            r"(\d{2}/\d{2}/\d{4})",
            r"(\d{2}-\d{2}-\d{4})",
            r"hasta\s+el\s+(\d{1,2}\s+de\s+\w+(?:\s+de\s+\d{4})?)",
            r"cierre[:\s]+(\d{1,2}\s+de\s+\w+(?:\s+de\s+\d{4})?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _extract_amount(self, text: str) -> str | None:
        """Extrae montos de texto libre en formato chileno."""
        patterns = [
            r"(\$[\d.,]+(?:\s*(?:CLP|UF|pesos|UFs))?)",
            r"(\d[\d.]*(?:\s*UF)s?)",
            r"(?:monto|máximo|financiamiento)[:\s]+(\$?[\d.,]+(?:\s*(?:CLP|UF))?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    async def extract(self, snapshot: Snapshot, fuente: Fuente, **_kwargs: Any) -> list[dict[str, str | None]]:
        logger.info("RssFeedScraper: iniciando extracción", fuente=fuente.nombre)

        try:
            root = ET.fromstring(snapshot.contenido_crudo)
        except ET.ParseError as e:
            msg = f"Error parseando XML del feed RSS para {fuente.nombre}"
            raise ExtractionError(msg) from e

        is_atom = root.tag.endswith("}feed") or root.tag == "feed"
        is_rss = root.tag.endswith("}rss") or root.tag == "rss"

        if not is_atom and not is_rss:
            msg = f"El contenido no es un feed RSS/Atom válido para {fuente.nombre}. Root tag: {root.tag}"
            raise ExtractionError(msg)

        if is_rss:
            items = root.findall(".//item")
        else:
            items = root.findall(".//atom:entry", _RSS_NAMESPACES)
            if not items:
                items = root.findall(".//entry")

        logger.info(
            "Items encontrados en feed",
            count=len(items),
            feed_type="Atom" if is_atom else "RSS",
            fuente=fuente.nombre,
        )

        resultados: list[dict[str, str | None]] = []
        processed = 0

        for item in items:
            if processed >= self._max_items:
                break

            try:
                title_el = item.find("title")
                if title_el is None and is_atom:
                    title_el = item.find(f"{{{_ATOM_NS}}}title")

                link_el = item.find("link")
                if link_el is None and is_atom:
                    link_el = item.find(f"{{{_ATOM_NS}}}link")

                desc_el = item.find("description")
                if desc_el is None:
                    desc_el = item.find("content:encoded", _RSS_NAMESPACES)
                if desc_el is None:
                    desc_el = item.find("summary")
                if desc_el is None and is_atom:
                    desc_el = item.find(f"{{{_ATOM_NS}}}summary")
                if desc_el is None and is_atom:
                    desc_el = item.find(f"{{{_ATOM_NS}}}content")

                pub_date_el = item.find("pubDate")
                if pub_date_el is None:
                    pub_date_el = item.find("dc:date", _RSS_NAMESPACES)
                if pub_date_el is None:
                    pub_date_el = item.find("published")
                if pub_date_el is None and is_atom:
                    pub_date_el = item.find(f"{{{_ATOM_NS}}}published")
                if pub_date_el is None and is_atom:
                    pub_date_el = item.find(f"{{{_ATOM_NS}}}updated")

                title = title_el.text.strip() if title_el is not None and title_el.text else ""
                description = ""
                if desc_el is not None and desc_el.text:
                    description = re.sub(r"<[^>]+>", "", desc_el.text).strip()

                link = ""
                if link_el is not None:
                    link = link_el.text.strip() if link_el.text else ""
                    if not link:
                        link = link_el.get("href", "")

                combined_text = f"{title} {description}"
                if not self._is_convocatoria_relevant(title, description):
                    logger.debug("Item de feed filtrado (no relevante)", title=title[:60])
                    continue

                identificador = link or "rss-" + hashlib.md5(title.encode("utf-8")).hexdigest()[:10]

                estado = self._detect_status(combined_text)
                fecha_cierre = self._extract_date(combined_text)
                monto = self._extract_amount(combined_text)

                item_data: dict[str, str | None] = {
                    "identificador": identificador,
                    "titulo": title or None,
                    "descripcion": description[:500] if description else None,
                    "url_detalle": link or None,
                    "estado": estado,
                    "fecha_cierre": fecha_cierre,
                    "monto": monto,
                }

                if not item_data["titulo"]:
                    continue

                resultados.append(item_data)
                processed += 1

            except Exception as e:
                logger.warning("Error parseando item de feed RSS", index=processed, exc=e)
                continue

        if not resultados and items:
            msg = f"Se encontraron items en el feed RSS pero ninguno pudo ser parseado para {fuente.nombre}"
            raise ExtractionError(msg)

        logger.info(
            "RssFeedScraper: extracción completada",
            items_relevantes=len(resultados),
            items_totales=len(items),
            fuente=fuente.nombre,
        )

        return resultados
