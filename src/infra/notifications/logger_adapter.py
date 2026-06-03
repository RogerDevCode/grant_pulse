"""
Adaptador base de notificaciones que envía los mensajes al sistema de logs.
Sirve como fallback y mecanismo de debug.
"""

from src.core.domain.entities import Convocatoria, EventoCambio, Fuente, NotificacionResult
from src.core.domain.ports import NotificationPort
from src.infra.logging import get_logger

logger = get_logger(__name__)


class LoggerNotificationAdapter(NotificationPort):
    """
    Adaptador de notificaciones que formatea y emite los eventos
    exclusivamente a través del logger estructurado.
    """

    async def notify_event(self, evento: EventoCambio, convocatoria: Convocatoria, fuente: Fuente) -> NotificacionResult:
        if not evento.es_relevante:
            return NotificacionResult(
                evento_id=evento.id,
                canal="LOGGER",
                destinatario="structlog",
                estado="SKIPPED",
                error_log="evento no relevante",
            )

        if evento.tipo == "APERTURA":
            mensaje = (
                f"NUEVA CONVOCATORIA en {fuente.nombre}\n"
                f"Título: {convocatoria.titulo}\n"
                f"Estado: {convocatoria.estado}\n"
                f"URL: {convocatoria.url_detalle}\n"
                f"Cierre: {convocatoria.fecha_cierre or 'No definido'}"
            )
            logger.info("NOTIFICACION_ENVIADA", tipo="APERTURA", mensaje=mensaje, fuente=fuente.nombre)

        elif evento.tipo == "MODIFICACION":
            cambios_str = ", ".join([f"{d.campo}: '{d.valor_anterior}' -> '{d.valor_nuevo}'" for d in evento.deltas])
            mensaje = (
                f"CAMBIO RELEVANTE en {fuente.nombre}\n"
                f"Título: {convocatoria.titulo}\n"
                f"Cambios: {cambios_str}\n"
                f"URL: {convocatoria.url_detalle}"
            )
            logger.info("NOTIFICACION_ENVIADA", tipo="MODIFICACION", mensaje=mensaje, fuente=fuente.nombre)

        return NotificacionResult(
            evento_id=evento.id,
            canal="LOGGER",
            destinatario="structlog",
            estado="ENVIADO",
        )
