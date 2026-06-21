"""
Caso de uso para el "Deep Scraping" o enriquecimiento de convocatorias.
Delega a un LLM la tarea de leer la url_detalle de una convocatoria
y extraer requisitos específicos, rubros y restricciones.
"""

from typing import Any, Protocol

from src.core.domain.entities import Convocatoria, DetalleEnriquecido, Fuente
from src.core.domain.ports import ConvocatoriaRepository, FuenteRepository
from src.infra.logging import get_logger

logger = get_logger(__name__)


class PageFetcherPort(Protocol):
    """Protocolo simple para aislar la descarga del HTML del detalle."""

    async def fetch_html(self, url: str) -> str:
        ...


class StructuredLLMClientPort(Protocol):
    """Protocolo específico para la extracción de detalle único."""

    async def extract_single_detail(
        self,
        html_content: str,
        base_url: str,
        institution_name: str = "",
        max_content_chars: int | None = None,
    ) -> dict[str, Any] | None:
        ...


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
        modelo DetalleEnriquecido y lo guarda en metadatos.
        """
        if not convocatoria.url_detalle:
            logger.info("Convocatoria sin url_detalle, ignorando enriquecimiento.", conv_id=convocatoria.id)
            convocatoria.metadatos["estado_enriquecimiento"] = "NO_APLICA"
            await self.convocatoria_repo.save(convocatoria)
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
            )

            if raw_detail:
                # Validamos contra el contrato Pydantic explícito
                detalle = DetalleEnriquecido(**raw_detail)
                convocatoria.metadatos["enriquecido"] = detalle.model_dump()
                convocatoria.metadatos["estado_enriquecimiento"] = "COMPLETADO"
                logger.info("Convocatoria enriquecida exitosamente", conv_id=convocatoria.id)
            else:
                convocatoria.metadatos["estado_enriquecimiento"] = "FALLIDO"
                logger.warning("LLM no retornó detalle válido", conv_id=convocatoria.id)

        except Exception as e:
            logger.error("Error durante el enriquecimiento de la convocatoria", conv_id=convocatoria.id, exc=e)
            convocatoria.metadatos["estado_enriquecimiento"] = "FALLIDO"

        await self.convocatoria_repo.save(convocatoria)
        return convocatoria
