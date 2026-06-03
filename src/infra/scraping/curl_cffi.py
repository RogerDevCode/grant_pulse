"""
Scraper genérico basado en curl_cffi con impersonación TLS.

Tier-2 en la jerarquía de scraping: se usa cuando httpx es bloqueado
por WAF que hace fingerprinting TLS (BigIP, Cloudflare, etc.),
pero el HTML es server-rendered (no necesita JS).

Reemplaza los scrapers legacy `CorfoScraper` y `ResilientFetcher`
con un solo adaptador configurable y reutilizable.
"""

import hashlib
from datetime import UTC, datetime
from typing import Any

from curl_cffi.requests import BrowserTypeLiteral, Session

from src.core.domain.entities import Fuente, Snapshot
from src.core.domain.exceptions import NetworkError
from src.core.domain.ports import ScraperPort
from src.infra.logging import get_logger

logger = get_logger(__name__)

_BROWSER_IMPERSONATE: BrowserTypeLiteral = "chrome120"

_DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}


class CurlCffiScraper(ScraperPort):
    """
    Scraper que usa curl_cffi para impersonar un navegador real a nivel TLS.

    Derrota WAFs que bloquean por TLS fingerprint (BigIP, Cloudflare, etc.).
    El HTML resultante se procesa con selectolax en extract().
    """

    def __init__(
        self,
        timeout: int = 30,
        impersonate: BrowserTypeLiteral = "chrome120",
    ) -> None:
        self._timeout = timeout
        self._impersonate: BrowserTypeLiteral = impersonate
        self._session = Session(impersonate=impersonate)

    async def fetch(self, fuente: Fuente) -> Snapshot:
        url = str(fuente.configuracion_reglas.url_busqueda)
        referer = str(fuente.url_base)
        logger.info("CurlCffiScraper: iniciando fetch", url=url, fuente=fuente.nombre, impersonate=self._impersonate)

        try:
            response = self._session.get(
                url,
                timeout=self._timeout,
                headers={
                    **_DEFAULT_HEADERS,
                    "Referer": referer,
                },
            )
        except Exception as e:
            msg = f"Error de red en curl_cffi para {fuente.nombre}: {e}"
            logger.error(msg, exc=e)
            raise NetworkError(msg) from e

        if response.status_code != 200:
            msg = f"curl_cffi: HTTP {response.status_code} para {fuente.nombre} en {url}"
            logger.error(msg, status=response.status_code, url=url, fuente=fuente.nombre)
            raise NetworkError(msg)

        content = response.text
        if not content or len(content.strip()) == 0:
            msg = f"curl_cffi: respuesta vacía (0 bytes) para {fuente.nombre} en {url}. Posible geo-blocking."
            logger.error(msg, url=url, fuente=fuente.nombre)
            raise NetworkError(msg)

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        logger.info(
            "CurlCffiScraper: fetch exitoso",
            url=url,
            fuente=fuente.nombre,
            content_length=len(content),
        )

        return Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=content,
            hash_contenido=content_hash,
            estado_ejecucion="SUCCESS",
        )

    async def extract(self, snapshot: Snapshot, fuente: Fuente, **_kwargs: Any) -> list[dict[str, str | None]]:
        """
        Delega la extracción al motor HtmlStaticScraper.
        curl_cffi es solo para el fetch; el parseo es idéntico al HTML estático.
        """
        from src.infra.scraping.html_static import HtmlStaticScraper

        static = HtmlStaticScraper()
        return await static.extract(snapshot, fuente, **_kwargs)
