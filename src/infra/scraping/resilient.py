"""
Adaptador de fetcher ultra-resiliente que utiliza curl_cffi.
Emula huellas dactilares de navegadores reales para saltar protecciones WAF/Cloudflare.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from curl_cffi import requests

from src.core.domain.entities import Fuente, Snapshot
from src.core.domain.exceptions import NetworkError
from src.core.domain.ports import ScraperPort
from src.infra.logging import get_logger

logger = get_logger(__name__)


class ResilientFetcher(ScraperPort):
    """
    Fetcher de grado militar para sitios con bloqueos agresivos.
    """

    async def fetch(self, fuente: Fuente) -> Snapshot:
        url = str(fuente.configuracion_reglas.url_busqueda)
        logger.info("Iniciando fetch resiliente (curl_cffi)", url=url)

        try:
            # Intentamos impersonar Chrome 120, que es muy común y confiable
            response = requests.get(
                url,
                impersonate="chrome120",
                timeout=30,
                verify=True,
            )

            if response.status_code != 200:
                logger.warning("Fallo en fetch resiliente", status=response.status_code, url=url)
                raise NetworkError(f"HTTP {response.status_code}")

            content = response.text
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

            return Snapshot(
                fuente_id=fuente.id,
                fecha_captura=datetime.now(UTC),
                contenido_crudo=content,
                hash_contenido=content_hash,
                estado_ejecucion="SUCCESS",
            )

        except Exception as e:
            msg = f"Error en ResilientFetcher para {url}: {e}"
            logger.error(msg, exc=e)
            raise NetworkError(msg) from e

    async def extract(self, snapshot: Snapshot, fuente: Fuente, **kwargs: Any) -> list[dict[str, str | None]]:
        # Este adaptador es principalmente para FETCH, pero por contrato implementamos extract
        # delegando al motor estático por defecto.
        from src.infra.scraping.html_static import HtmlStaticScraper

        static = HtmlStaticScraper()
        return await static.extract(snapshot, fuente, **kwargs)
