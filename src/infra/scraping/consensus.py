"""
Orquestador de consenso para validación de datos mediante doble lectura.
Implementa la estrategia de "Consensus Mode" para asegurar calidad de datos.
"""

import asyncio
from typing import Any

from src.core.domain.entities import Fuente, Snapshot
from src.core.domain.ports import ScraperPort
from src.infra.logging import get_logger

logger = get_logger(__name__)


class ConsensusScraper(ScraperPort):
    """
    Scraper que ejecuta dos motores en paralelo y busca consenso.
    Si los resultados difieren, puede usar un tercer motor (LLM) como árbitro.
    """

    def __init__(
        self,
        primary: ScraperPort,
        secondary: ScraperPort,
        referee: ScraperPort | None = None,
    ) -> None:
        self.primary = primary
        self.secondary = secondary
        self.referee = referee

    async def fetch(self, fuente: Fuente) -> Snapshot:
        # El fetch se hace con el primario usualmente
        return await self.primary.fetch(fuente)

    async def extract(
        self,
        snapshot: Snapshot,
        fuente: Fuente,
        **kwargs: Any,
    ) -> list[dict[str, str | None]]:
        logger.info(
            "ConsensusScraper: iniciando extracción paralela",
            fuente=fuente.nombre,
            primary=self.primary.__class__.__name__,
            secondary=self.secondary.__class__.__name__,
        )

        # Ejecutamos ambas extracciones en paralelo
        results = await asyncio.gather(
            self.primary.extract(snapshot, fuente, **kwargs),
            self.secondary.extract(snapshot, fuente, **kwargs),
            return_exceptions=True,
        )

        res_primary = results[0] if not isinstance(results[0], Exception) else []
        res_secondary = results[1] if not isinstance(results[1], Exception) else []

        if isinstance(results[0], Exception):
            logger.warning("Consensus: Error en scraper primario", exc=results[0])
        if isinstance(results[1], Exception):
            logger.warning("Consensus: Error en scraper secundario", exc=results[1])

        # Lógica de consenso simple: si coinciden en cantidad y títulos, alta confianza.
        titles_primary = {r.get("titulo") for r in res_primary if r.get("titulo")}
        titles_secondary = {r.get("titulo") for r in res_secondary if r.get("titulo")}

        if titles_primary == titles_secondary and len(res_primary) > 0:
            logger.info("Consensus: Coincidencia total (Gold Standard)", items=len(res_primary))
            return res_primary

        logger.warning(
            "Consensus: Discrepancia detectada",
            primary_count=len(res_primary),
            secondary_count=len(res_secondary),
        )

        # Si hay árbitro (LLM), lo invocamos para decidir
        if self.referee and (len(res_primary) != len(res_secondary) or titles_primary != titles_secondary):
            logger.info("Consensus: Invocando árbitro (LLM) por discrepancia")
            return await self.referee.extract(snapshot, fuente, **kwargs)

        # Fallback: preferimos el que tenga más items o el primario
        return res_primary if len(res_primary) >= len(res_secondary) else res_secondary
