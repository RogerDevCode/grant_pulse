"""Extractor heurístico usando Trafilatura para extraer convocatorias sin reglas fijas."""

import asyncio
from typing import Any

import trafilatura
from pydantic import HttpUrl

from src.core.domain.entities import Fuente, Snapshot
from src.core.domain.exceptions import ExtractionError
from src.core.domain.ports import ScraperPort
from src.infra.logging import get_logger
from src.infra.scraping.html_static import HtmlStaticScraper

logger = get_logger(__name__)


class TrafilaturaScraper(ScraperPort):
    """
    Scraper que utiliza la heurística de Trafilatura para limpieza y extracción de texto principal.
    Evita bloqueos del event loop offloadeando la tarea CPU-bound a un thread.
    """

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout
        self._html_fetcher = HtmlStaticScraper(timeout=timeout)

    async def fetch(self, fuente: Fuente) -> Snapshot:
        """Delega el fetch a la implementación HTTPX de HtmlStaticScraper."""
        return await self._html_fetcher.fetch(fuente)

    def _extract_sync(self, html_crudo: str, url_base: str | HttpUrl) -> list[dict[str, str | None]]:
        """Extrae el contenido usando Trafilatura de forma síncrona."""
        # Trafilatura extract retorna el texto limpio
        extracted_text = trafilatura.extract(
            html_crudo, include_links=True, include_formatting=True, include_images=False, url=str(url_base)
        )
        if not extracted_text:
            return []

        # Como Trafilatura retorna un bloque de texto plano/markdown con links,
        # lo procesamos para intentar encontrar bloques que parezcan convocatorias.
        # Al no tener una estructura clara, devolveremos el documento completo como
        # un solo item gigante para que el LLM o fuzzy logic lo parseen,
        # o lo dividimos por encabezados.
        # En esta fase 1, devolvemos un único "item" con el texto extraído como descripción.
        # Si hubiera necesidad de particionarlo, se puede mejorar después.

        # Ojo: esto es un fallback. El enriquecedor posterior se encarga de parsear mejor si es necesario.
        return [
            {
                "identificador": "TRAF-AUTO",
                "titulo": "Contenido Extraído (Trafilatura)",
                "descripcion": extracted_text,
                "url_detalle": str(url_base),
                "estado": "DESCONOCIDO",
            }
        ]

    async def extract(
        self,
        snapshot: Snapshot,
        fuente: Fuente,
        **kwargs: Any,  # noqa: ARG002
    ) -> list[dict[str, str | None]]:
        """Ejecuta la extracción de Trafilatura en un thread pool."""
        try:
            return await asyncio.to_thread(self._extract_sync, snapshot.contenido_crudo, fuente.url_base)
        except Exception as e:
            logger.error("Trafilatura falló al extraer", fuente_id=str(fuente.id), exc=e)
            raise ExtractionError(f"Error de Trafilatura: {e}") from e
