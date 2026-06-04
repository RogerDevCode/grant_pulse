"""
Scraper multi-subpágina para FOSIS (fosis.gob.cl).

FOSIS usa Django CMS con programas distribuidos en 5 categorías:
- /es/programas/autonomia-economica/     (10+ programas)
- /es/programas/autonomia-desarrollo/    (11+ programas)
- /es/programas/habitabilidad/           (1-2 programas)
- /es/programas/innova-fosis/            (FAQ, no programas con btn)

Y una página de convocatorias de alianzas:
- /es/convocatoria-alianzas/             (~20 convocatorias regionales)

Estrategia:
1. fetch(): descarga todas las subpáginas en paralelo
2. extract(): parsea cada HTML y extrae:
   - Programas: div[style*=background-color] con h2 + a.btn[href*=/programas/]
   - Convocatorias alianzas: a[href*=/convocatoria-alianzas/...] con texto > 15 chars
3. Deduplica por URL del programa (puede aparecer en múltiples categorías)
"""

import hashlib
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

_FOSIS_BASE = "https://www.fosis.gob.cl"

_PROGRAM_PAGES = [
    ("autonomia-economica", f"{_FOSIS_BASE}/es/programas/autonomia-economica/"),
    ("autonomia-desarrollo", f"{_FOSIS_BASE}/es/programas/autonomia-desarrollo/"),
    ("habitabilidad", f"{_FOSIS_BASE}/es/programas/habitabilidad/"),
    ("innova-fosis", f"{_FOSIS_BASE}/es/programas/innova-fosis/"),
]

_ALIANZAS_PAGE = f"{_FOSIS_BASE}/es/convocatoria-alianzas/"

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


class FosisMultiPageScraper(ScraperPort):
    """
    Scraper que agrega programas y convocatorias desde múltiples
    subpáginas de FOSIS.
    """

    def __init__(self, timeout: int = 20) -> None:
        self._timeout = timeout

    async def fetch(self, fuente: Fuente) -> Snapshot:
        urls = [(name, url) for name, url in _PROGRAM_PAGES]
        urls.append(("convocatoria-alianzas", _ALIANZAS_PAGE))

        logger.info(
            "FosisMultiPageScraper: realizando fetch multi-página",
            pages=len(urls),
            fuente=fuente.nombre,
        )

        pages_html: dict[str, str] = {}

        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers=_REALISTIC_HEADERS,
            follow_redirects=True,
        ) as client:
            for name, url in urls:
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    pages_html[name] = response.text
                    logger.debug(
                        "FosisMultiPageScraper: página descargada",
                        page=name,
                        chars=len(response.text),
                    )
                except httpx.HTTPStatusError as e:
                    msg = f"Error HTTP {e.response.status_code} en página {name} de FOSIS: {url}"
                    logger.error(msg, exc=e)
                    raise NetworkError(msg) from e
                except httpx.RequestError as e:
                    msg = f"Error de red en página {name} de FOSIS: {url}: {e}"
                    logger.error(msg, exc=e)
                    raise NetworkError(msg) from e

        combined = self._combine_pages(pages_html)
        content_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()

        return Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=combined,
            hash_contenido=content_hash,
            estado_ejecucion="SUCCESS",
        )

    async def extract(
        self, snapshot: Snapshot, fuente: Fuente, **_kwargs: Any
    ) -> list[dict[str, str | None]]:
        logger.info(
            "FosisMultiPageScraper: iniciando extracción multi-página",
            fuente=fuente.nombre,
        )

        try:
            pages = self._split_pages(snapshot.contenido_crudo)
        except Exception as e:
            msg = f"Error parseando contenido combinado de FOSIS para {fuente.nombre}"
            raise ExtractionError(msg) from e

        resultados: list[dict[str, str | None]] = []
        seen_urls: set[str] = set()

        for page_name, html in pages.items():
            try:
                tree = HTMLParser(html)
            except Exception as e:
                logger.warning(
                    "FosisMultiPageScraper: error parseando página, saltando",
                    page=page_name,
                    error=str(e),
                )
                continue

            if page_name == "convocatoria-alianzas":
                self._extract_alianzas(tree, resultados, seen_urls)
            else:
                self._extract_programs(tree, page_name, resultados, seen_urls)

        logger.info(
            "FosisMultiPageScraper: extracción completada",
            items=len(resultados),
            fuente=fuente.nombre,
        )
        return resultados

    def _combine_pages(self, pages_html: dict[str, str]) -> str:
        parts: list[str] = []
        for name, html in pages_html.items():
            parts.append(f"===PAGE:{name}===\n{html}\n===ENDPAGE===\n")
        return "".join(parts)

    def _split_pages(self, combined: str) -> dict[str, str]:
        pages: dict[str, str] = {}
        current_name: str | None = None
        current_chunks: list[str] = []

        for line in combined.split("\n"):
            if line.startswith("===PAGE:") and line.endswith("==="):
                if current_name is not None:
                    pages[current_name] = "\n".join(current_chunks)
                current_name = line[8:-3]
                current_chunks = []
            elif line == "===ENDPAGE===":
                if current_name is not None:
                    pages[current_name] = "\n".join(current_chunks)
                current_name = None
                current_chunks = []
            elif current_name is not None:
                current_chunks.append(line)

        if current_name is not None:
            pages[current_name] = "\n".join(current_chunks)

        return pages

    def _extract_programs(
        self,
        tree: HTMLParser,
        _page_name: str,
        resultados: list[dict[str, str | None]],
        seen_urls: set[str],
    ) -> None:
        cards = tree.css("div[style*='background-color']")
        for card in cards:
            h2 = card.css_first("h2")
            btn = card.css_first("a.btn")

            if not h2 or not btn:
                continue

            href = btn.attributes.get("href", "")
            if not href or "/programas/" not in href:
                continue

            full_url = urljoin(_FOSIS_BASE, href)

            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            title = h2.text(strip=True)
            if not title or len(title) < 3:
                continue

            p = card.css_first("p")
            description = p.text(strip=True)[:500] if p else None

            identificador = href.rstrip("/").split("/")[-1]
            if not identificador:
                identificador = "fosis-" + hashlib.md5(title.encode("utf-8")).hexdigest()[:10]

            estado = _detect_status(f"{title} {description or ''}")

            item: dict[str, str | None] = {
                "identificador": identificador,
                "titulo": title,
                "descripcion": description,
                "url_detalle": full_url,
                "estado": estado,
                "fecha_cierre": None,
                "monto": None,
            }
            resultados.append(item)

    def _extract_alianzas(
        self,
        tree: HTMLParser,
        resultados: list[dict[str, str | None]],
        seen_urls: set[str],
    ) -> None:
        for a in tree.css("a"):
            href = a.attributes.get("href", "")
            if not href:
                continue
            if "/convocatoria-alianzas/" not in href:
                continue
            if href == "/es/convocatoria-alianzas/" or href == _ALIANZAS_PAGE:
                continue
            if "edit" in href or "readid" in href or "readspeaker" in href.lower():
                continue

            text = a.text(strip=True)
            if not text or len(text) < 15:
                continue

            full_url = urljoin(_FOSIS_BASE, href)

            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            last_segment = href.rstrip("/").split("/")[-1]
            if not last_segment or last_segment == "convocatoria-alianzas":
                continue

            identificador = f"alianza-{last_segment}"
            estado = _detect_status(text)

            item: dict[str, str | None] = {
                "identificador": identificador,
                "titulo": text,
                "descripcion": f"Convocatoria de alianza institucional: {text}",
                "url_detalle": full_url,
                "estado": estado,
                "fecha_cierre": None,
                "monto": None,
            }
            resultados.append(item)
