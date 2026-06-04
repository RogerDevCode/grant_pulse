"""
Scraper especializado para la homepage de SUBDERE (subdere.gob.cl).

El sitio bloquea /programas y la mayoría de rutas con 403 (WAF Apache).
La homepage (/) retorna 200 y contiene:
- Noticias relevantes (slideshow + listado) con títulos, fechas y resumen
- Programas destacados en el sidebar (4 items fijos)
- Menú de 3 divisiones de programas

Estrategia:
1. fetch(): Descarga la homepage con httpx (retorna 200)
2. extract(): Parsea el HTML y extrae:
   - Noticias relevantes (filtradas por keywords de convocatorias)
   - Programas destacados del sidebar como items estáticos
"""

import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, urljoin

import httpx
from selectolax.lexbor import LexborHTMLParser

from src.core.domain.entities import Fuente, Snapshot
from src.core.domain.estado_normalizer import normalize_estado
from src.core.domain.exceptions import ExtractionError, NetworkError
from src.core.domain.ports import ScraperPort
from src.infra.logging import get_logger

logger = get_logger(__name__)

_SUBDERE_BASE = "https://www.subdere.gob.cl/"

_CONVOCATORIA_KEYWORDS = re.compile(
    r"\b(convocatoria|concurso|fondo|programa|postulaci[óo]n|licitaci[óo]n|"
    r"financiamiento|subvenci[óo]n|beca|proyecto|emprende|semilla|"
    r"capital|crece|innova|abiert[oa]|vigente|cierre|apertura|"
    r"revive|mejoramiento|patrimonio|municipal|regional|"
    r"fortalecimiento|inversi[óo]n|infraestructura|descentralizaci[óo]n|"
    r"inducci[óo]n|diagn[óo]stico|contingencia|"
    r"ejecuci[óo]n presupuestaria|plan regional)\b",
    re.IGNORECASE,
)

_DATE_PATTERN = re.compile(
    r"(\w+,\s+\d{1,2}\s+\w+\s+\d{4})|(\d{1,2}\s+de\s+\w+(?:\s+de\s+\d{4})?)|"
    r"(\w+\s+\d{1,2},?\s+\d{4})",
)

_REALISTIC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9",
}


def _detect_status(text: str) -> str:
    return normalize_estado(text)


def _extract_date(text: str) -> str | None:
    match = _DATE_PATTERN.search(text)
    if match:
        return match.group(0).strip()
    return None


def _is_relevant(title: str, body: str) -> bool:
    combined = f"{title} {body}"
    return bool(_CONVOCATORIA_KEYWORDS.search(combined))


class SubdereHomepageScraper(ScraperPort):
    """
    Scraper que extrae convocatorias y noticias relevantes desde
    la homepage de SUBDERE, única página accesible del sitio.
    """

    def __init__(self, timeout: int = 20) -> None:
        self._timeout = timeout

    async def fetch(self, fuente: Fuente) -> Snapshot:
        url = _SUBDERE_BASE
        logger.info("SubdereHomepageScraper: realizando fetch", url=url, fuente=fuente.nombre)

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                headers=_REALISTIC_HEADERS,
                follow_redirects=True,
            ) as client:
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

        return Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=html_content,
            hash_contenido=content_hash,
            estado_ejecucion="SUCCESS",
        )

    async def extract(
        self, snapshot: Snapshot, fuente: Fuente, **_kwargs: Any
    ) -> list[dict[str, str | None]]:
        logger.info("SubdereHomepageScraper: iniciando extracción", fuente=fuente.nombre)

        try:
            tree = LexborHTMLParser(snapshot.contenido_crudo)
        except Exception as e:
            msg = f"Error parseando HTML de homepage SUBDERE para {fuente.nombre}"
            raise ExtractionError(msg) from e

        resultados: list[dict[str, str | None]] = []
        seen_hrefs: set[str] = set()

        self._extract_news_items(tree, fuente, resultados, seen_hrefs)
        self._extract_featured_programs(tree, fuente, resultados, seen_hrefs)

        if not resultados:
            logger.warning(
                "No se encontraron items relevantes en homepage SUBDERE",
                fuente=fuente.nombre,
            )
            return []

        logger.info(
            "SubdereHomepageScraper: extracción completada",
            items=len(resultados),
            fuente=fuente.nombre,
        )
        return resultados

    def _extract_news_items(
        self,
        tree: LexborHTMLParser,
        fuente: Fuente,  # noqa: ARG002
        resultados: list[dict[str, str | None]],
        seen_hrefs: set[str],
    ) -> None:
        seen_titles: set[str] = set()

        for a in tree.css("a"):
            href = a.attributes.get("href", "")
            if not href or "sala-de-prensa" not in href:
                continue
            if "facebook" in href or "twitter" in href or "flickr" in href:
                continue

            title = a.text(strip=True)
            if not title or len(title) < 15:
                continue

            if href in seen_hrefs or title in seen_titles:
                continue
            seen_hrefs.add(href)
            seen_titles.add(title)

            body = ""
            date_str = ""
            parent = a.parent
            for _ in range(5):
                if parent is None:
                    break
                parent = parent.parent
            if parent:
                ctx = parent.text(separator=" ", strip=True)
                date_match = _DATE_PATTERN.search(ctx)
                date_str = date_match.group(0).strip() if date_match else ""
                body = ctx.replace(title, "").replace(date_str, "").strip()
                body = re.sub(
                    r"(Facebook Like|Compartir en Facebook|Tweet Widget|Leer más.*?\.|"
                    r"Mayo\s+\d+,\s+\d{4}|Junio\s+\d+,\s+\d{4}|"
                    r"Enero|Febrero|Marzo|Abril|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre\s+\d+,\s+\d{4})",
                    "",
                    body,
                ).strip()

            if not _is_relevant(title, body):
                logger.debug("Noticia SUBDERE filtrada (no relevante)", title=title[:60])
                continue

            full_url = urljoin(_SUBDERE_BASE, href)
            identificador = unquote(href.rstrip("/").split("/")[-1])
            if not identificador:
                identificador = "subdere-news-" + hashlib.md5(title.encode("utf-8")).hexdigest()[:10]

            estado = _detect_status(f"{title} {body}")
            fecha_cierre = _extract_date(f"{title} {body}")

            item: dict[str, str | None] = {
                "identificador": identificador,
                "titulo": title,
                "descripcion": body[:500] if body else None,
                "url_detalle": full_url,
                "estado": estado,
                "fecha_cierre": fecha_cierre,
                "monto": None,
            }
            resultados.append(item)

    def _extract_featured_programs(
        self,
        tree: LexborHTMLParser,
        fuente: Fuente,  # noqa: ARG002
        resultados: list[dict[str, str | None]],
        seen_hrefs: set[str],
    ) -> None:
        for a in tree.css("a"):
            href = a.attributes.get("href", "")
            if not href or "/programas/divisi" not in href:
                continue

            last_segment = href.rstrip("/").split("/")[-1]
            if "division" in last_segment.lower() or "division" in last_segment.lower():
                continue

            title = a.text(strip=True)
            if not title or len(title) < 5:
                continue

            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)

            full_url = urljoin(_SUBDERE_BASE, href)
            identificador = unquote(last_segment)

            item: dict[str, str | None] = {
                "identificador": identificador,
                "titulo": title,
                "descripcion": f"Programa destacado en homepage SUBDERE: {title}",
                "url_detalle": full_url,
                "estado": "DESCONOCIDO",
                "fecha_cierre": None,
                "monto": None,
            }
            resultados.append(item)
