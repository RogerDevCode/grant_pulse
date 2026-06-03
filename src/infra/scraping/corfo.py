"""
Estrategia especializada para CORFO.
Utiliza curl_cffi para emular el TLS fingerprint de un navegador real y saltar el WAF.
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


class CorfoScraper(ScraperPort):
    """
    Scraper de élite para CORFO.
    Especializado en saltar el error 403 Forbidden persistente.
    """

    async def fetch(self, fuente: Fuente) -> Snapshot:
        url = str(fuente.configuracion_reglas.url_busqueda)
        logger.info("Iniciando fetch especializado CORFO", url=url)

        try:
            # curl_cffi emula perfectamente el TLS Hello de un navegador (chrome120)
            # Esto suele ser lo que detectan los WAFs para bloquear peticiones httpx/requests
            response = requests.get(
                url,
                impersonate="chrome120",
                timeout=30,
                headers={
                    "Referer": "https://www.corfo.cl/",
                    "Accept-Language": "es-CL,es;q=0.9",
                },
            )

            if response.status_code != 200:
                logger.error("CORFO respondió con error", status=response.status_code, text=response.text[:200])
                raise NetworkError(f"CORFO respondió {response.status_code}")

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
            msg = f"Fallo catastrófico en CorfoScraper: {e}"
            logger.error(msg, exc=e)
            raise NetworkError(msg) from e

    async def extract(self, snapshot: Snapshot, fuente: Fuente, **kwargs: Any) -> list[dict[str, str | None]]:  # noqa: ARG002
        """
        Delega la extracción al motor de LLM (GLM-5.1) para máxima precisión,
        ya que el HTML de CORFO es muy ruidoso.
        """
        from src.infra.scraping.llm_scraper import LlmScraper

        # Usamos el LlmScraper interno para procesar el HTML capturado por CorfoScraper
        llm_engine = LlmScraper()
        return await llm_engine.extract(snapshot, fuente, **kwargs)
