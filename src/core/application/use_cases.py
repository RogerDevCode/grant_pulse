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
from src.core.domain.vigencia import filtrar_vigentes
from src.infra.logging import get_logger

logger = get_logger(__name__)


class MonitoreoUseCase:
    """Caso de uso principal para ejecutar un ciclo de monitoreo sobre una fuente."""

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
        4. Vigencia filter (filtrar_vigentes)
        5. Obtain previous state (ConvocatoriaRepository)
        6. Detect Changes (ChangeDetectorService)
        7. Persist (Repositories)
        8. Notify (NotificationPort) + Persist Notification Results
        """
        logger.info("Iniciando caso de uso de monitoreo", fuente_id=str(fuente.id), fuente_nombre=fuente.nombre)
        errores_persistencia = 0
        try:
            snapshot = await self.scraper.fetch(fuente)

            raw_items = await self.scraper.extract(snapshot, fuente)

            nuevas_convocatorias = DataNormalizer.normalize_and_map(raw_items, fuente)

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

            pre_vigencia = len(nuevas_convocatorias)
            nuevas_convocatorias = filtrar_vigentes(nuevas_convocatorias)
            descartadas_vigencia = pre_vigencia - len(nuevas_convocatorias)
            if descartadas_vigencia > 0:
                logger.info(
                    "Convocatorias descartadas por vigencia",
                    fuente=fuente.nombre,
                    antes=pre_vigencia,
                    despues=len(nuevas_convocatorias),
                    descartadas=descartadas_vigencia,
                )

            antiguas_lista = await self.convocatoria_repo.get_all_by_fuente(fuente.id)
            antiguas_dict = {c.identificador_externo: c for c in antiguas_lista}

            eventos = ChangeDetectorService.detect_changes(nuevas_convocatorias, antiguas_dict, fuente)

            nuevas_dict = {c.id: c for c in nuevas_convocatorias}

            await self.snapshot_repo.save(snapshot)

            for conv in nuevas_convocatorias:
                await self.convocatoria_repo.save(conv)

            await self.convocatoria_repo.flush()

            for evento in eventos:
                await self.convocatoria_repo.save_evento_cambio(evento, snapshot.id)

            if self.notifier:
                for evento in eventos:
                    if evento.es_relevante:
                        conv_notif = nuevas_dict.get(evento.convocatoria_id)
                        if conv_notif:
                            notif_result: NotificacionResult | None = None
                            try:
                                notif_result = await self.notifier.notify_event(evento, conv_notif, fuente)
                            except NotificationError as e:
                                logger.error(
                                    "Notificación falló para evento",
                                    evento_id=str(evento.id),
                                    error=str(e),
                                    exc=e,
                                )
                                notif_result = NotificacionResult(
                                    evento_id=evento.id,
                                    canal="UNKNOWN",
                                    destinatario="fallo",
                                    estado="FALLIDO",
                                    error_log=str(e),
                                )

                            if notif_result is not None and self.notificacion_repo:
                                try:
                                    await self.notificacion_repo.save(notif_result)
                                except Exception as e:
                                    logger.error(
                                        "No se pudo persistir resultado de notificación",
                                        evento_id=str(evento.id),
                                        exc=e,
                                    )
                                    errores_persistencia += 1

            status = "exitosamente" if errores_persistencia == 0 else "con errores de persistencia de notificaciones"
            logger.info(
                f"Monitoreo finalizado {status}",
                fuente_id=str(fuente.id),
                nuevas_encontradas=len(nuevas_convocatorias),
                eventos_generados=len(eventos),
                errores_persistencia_notificaciones=errores_persistencia,
            )
            return eventos

        except GrantPulseError as e:
            logger.error("Fallo controlado en monitoreo de fuente", fuente_id=str(fuente.id), exc=e)
            raise
        except Exception as e:
            logger.error("Error catastrófico no esperado en monitoreo", fuente_id=str(fuente.id), exc=e)
            raise
