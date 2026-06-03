"""Casos de uso principales (Application Services)."""

from src.core.application.normalizer import DataNormalizer
from src.core.domain.entities import Convocatoria, EventoCambio, Fuente, NotificacionResult
from src.core.domain.exceptions import GrantPulseError, NotificationError
from src.core.domain.ports import (
    ConvocatoriaRepository,
    NotificacionRepository,
    NotificationPort,
    ScraperPort,
    SnapshotRepository,
)
from src.core.domain.services import ChangeDetectorService
from src.infra.logging import get_logger

logger = get_logger(__name__)


class MonitoreoUseCase:
    """
    Caso de uso principal para ejecutar un ciclo de monitoreo sobre una fuente.
    """

    def __init__(
        self,
        scraper: ScraperPort,
        snapshot_repo: SnapshotRepository,
        convocatoria_repo: ConvocatoriaRepository,
        notifier: NotificationPort | None = None,
        notificacion_repo: NotificacionRepository | None = None,
    ) -> None:
        self.scraper = scraper
        self.snapshot_repo = snapshot_repo
        self.convocatoria_repo = convocatoria_repo
        self.notifier = notifier
        self.notificacion_repo = notificacion_repo

    async def ejecutar_monitoreo(self, fuente: Fuente) -> list[EventoCambio]:
        """
        Flujo central:
        1. Fetch (Scraper)
        2. Extract (Scraper)
        3. Normalize (DataNormalizer)
        4. Obtain previous state (ConvocatoriaRepository)
        5. Detect Changes (ChangeDetectorService)
        6. Persist (Repositories)
        7. Notify (NotificationPort) + Persist Notification Results
        """
        logger.info("Iniciando caso de uso de monitoreo", fuente_id=str(fuente.id), fuente_nombre=fuente.nombre)
        try:
            # 1. Fetch
            snapshot = await self.scraper.fetch(fuente)

            # 2. Extract
            raw_items = await self.scraper.extract(snapshot, fuente)

            # 3. Normalize
            nuevas_convocatorias = DataNormalizer.normalize_and_map(raw_items, fuente)

            # 3b. Deduplicate by identificador_externo (keep last occurrence)
            seen: dict[str, Convocatoria] = {}
            for conv in nuevas_convocatorias:
                seen[conv.identificador_externo] = conv
            nuevas_convocatorias = list(seen.values())
            if len(seen) < len(raw_items):
                logger.info(
                    "Convocatorias deduplicadas por identificador_externo",
                    antes=len(raw_items),
                    despues=len(nuevas_convocatorias),
                    fuente=fuente.nombre,
                )

            # 4. Obtener estado anterior
            antiguas_lista = await self.convocatoria_repo.get_all_by_fuente(fuente.id)
            antiguas_dict = {c.identificador_externo: c for c in antiguas_lista}

            # 5. Detección de Cambios
            eventos = ChangeDetectorService.detect_changes(nuevas_convocatorias, antiguas_dict, fuente)

            # Construir dict DESPUÉS de detect_changes (que sincroniza IDs)
            nuevas_dict = {c.id: c for c in nuevas_convocatorias}

            # 6. Persistencia
            await self.snapshot_repo.save(snapshot)

            for conv in nuevas_convocatorias:
                await self.convocatoria_repo.save(conv)

            await self.convocatoria_repo.flush()

            for evento in eventos:
                await self.convocatoria_repo.save_evento_cambio(evento, snapshot.id)

            # 7. Notificaciones + Persistencia de resultados
            if self.notifier:
                for evento in eventos:
                    if evento.es_relevante:
                        conv_notif = nuevas_dict.get(evento.convocatoria_id)
                        if conv_notif:
                            try:
                                result = await self.notifier.notify_event(evento, conv_notif, fuente)
                            except NotificationError as e:
                                logger.error(
                                    "Notificación falló para evento",
                                    evento_id=str(evento.id),
                                    error=str(e),
                                    exc=e,
                                )
                                result = NotificacionResult(
                                    evento_id=evento.id,
                                    canal="UNKNOWN",
                                    destinatario="fallo",
                                    estado="FALLIDO",
                                    error_log=str(e),
                                )

                            if self.notificacion_repo:
                                try:
                                    await self.notificacion_repo.save(result)
                                except Exception as e:
                                    logger.error(
                                        "No se pudo persistir resultado de notificación",
                                        evento_id=str(evento.id),
                                        exc=e,
                                    )

            logger.info(
                "Monitoreo finalizado exitosamente",
                fuente_id=str(fuente.id),
                nuevas_encontradas=len(nuevas_convocatorias),
                eventos_generados=len(eventos),
            )
            return eventos

        except GrantPulseError as e:
            logger.error("Fallo controlado en monitoreo de fuente", fuente_id=str(fuente.id), exc=e)
            raise
        except Exception as e:
            logger.error("Error catastrófico no esperado en monitoreo", fuente_id=str(fuente.id), exc=e)
            raise
