"""
Caso de uso para el "Deep Scraping" o enriquecimiento de convocatorias.
Delega a un LLM la tarea de leer la url_detalle de una convocatoria
y extraer requisitos específicos, rubros y restricciones.
"""

from typing import Any, Protocol

from src.core.domain.entities import Convocatoria, DetalleEnriquecido
from src.core.domain.ports import ConvocatoriaRepository, FuenteRepository
from src.infra.logging import get_logger

logger = get_logger(__name__)


class PageFetcherPort(Protocol):
    """Protocolo simple para aislar la descarga del HTML del detalle."""

    async def fetch_html(self, url: str) -> str: ...


class StructuredLLMClientPort(Protocol):
    """Protocolo específico para la extracción de detalle único."""

    async def extract_single_detail(
        self,
        html_content: str,
        base_url: str,
        institution_name: str = "",
        max_content_chars: int | None = None,
        institution_hint: str | None = None,
    ) -> dict[str, Any] | None: ...


class EnriquecerConvocatoriaUseCase:
    """Caso de uso para extraer datos profundos de una convocatoria usando LLM."""

    def __init__(
        self,
        convocatoria_repo: ConvocatoriaRepository,
        fuente_repo: FuenteRepository,
        fetcher: PageFetcherPort,
        llm_client: StructuredLLMClientPort,
    ) -> None:
        self.convocatoria_repo = convocatoria_repo
        self.fuente_repo = fuente_repo
        self.fetcher = fetcher
        self.llm_client = llm_client

    async def execute(self, convocatoria: Convocatoria) -> Convocatoria:
        """
        Descarga el detalle de una convocatoria, pide al LLM que extraiga el
        modelo DetalleEnriquecido y lo guarda SOLO en metadatos.

        Invariante: nunca sobreescribe campos principales (region, monto,
        fechas, estado, titulo, descripcion) que ya fueron obtenidos por el
        scraper. El LLM es el último recurso y sus resultados van a
        metadatos['enriquecido'] exclusivamente.
        """
        if not convocatoria.url_detalle:
            logger.info("Convocatoria sin url_detalle, ignorando enriquecimiento.", conv_id=convocatoria.id)
            convocatoria.estado_enriquecimiento = "NO_APLICA"
            await self.convocatoria_repo.save_enriched_data(convocatoria)
            return convocatoria

        fuente_id = int(str(convocatoria.fuente_id))
        fuente = await self.fuente_repo.get_by_id(fuente_id)
        if not fuente:
            logger.error("Fuente no encontrada para la convocatoria.", fuente_id=convocatoria.fuente_id)
            return convocatoria

        try:
            logger.info("Iniciando fetch para deep scraping", url=str(convocatoria.url_detalle))
            html_content = await self.fetcher.fetch_html(str(convocatoria.url_detalle))

            raw_detail = await self.llm_client.extract_single_detail(
                html_content=html_content,
                base_url=str(convocatoria.url_detalle),
                institution_name=fuente.nombre,
                institution_hint=fuente.configuracion_reglas.llm_prompt_hint,
            )

            if raw_detail:
                # Validamos contra el contrato Pydantic explícito
                detalle = DetalleEnriquecido(**raw_detail)
                # El LLM SOLO escribe en campos dedicados, nunca en campos principales
                convocatoria.detalles_llm = detalle.model_dump()
                convocatoria.estado_enriquecimiento = "COMPLETADO"
                logger.info("Convocatoria enriquecida exitosamente", conv_id=convocatoria.id)
            else:
                convocatoria.estado_enriquecimiento = "FALLIDO"
                logger.warning("LLM no retornó detalle válido", conv_id=convocatoria.id)

        except Exception as e:
            logger.error("Error durante el enriquecimiento de la convocatoria", conv_id=convocatoria.id, exc=e)
            convocatoria.estado_enriquecimiento = "FALLIDO"

        # Guardar SOLO campos de enriquecimiento: no toca region, monto, fechas ni estado
        await self.convocatoria_repo.save_enriched_data(convocatoria)
        return convocatoria


class EnriquecerLoteUseCase:
    """Implementa el patrón Outbox para el enriquecimiento diferido."""

    def __init__(self, convocatoria_repo: ConvocatoriaRepository, enricher_uc: EnriquecerConvocatoriaUseCase) -> None:
        self.convocatoria_repo = convocatoria_repo
        self.enricher_uc = enricher_uc

    async def execute(self, limit: int = 50) -> tuple[int, int]:
        pendientes = await self.convocatoria_repo.get_pending_enrichment(limit=limit)
        if not pendientes:
            logger.info("No hay convocatorias pendientes de enriquecimiento")
            return 0, 0

        exitos, fallas = 0, 0
        for conv in pendientes:
            try:
                await self.enricher_uc.execute(conv)
                if conv.estado_enriquecimiento == "COMPLETADO":
                    exitos += 1
                else:
                    fallas += 1
            except Exception as e:
                logger.error("Fallo inesperado al enriquecer convocatoria", conv_id=conv.id, exc=e)
                fallas += 1

        return exitos, fallas
