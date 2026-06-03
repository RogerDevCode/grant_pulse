"""
Coordinador de múltiples adaptadores de notificación.
Permite enviar alertas a varios canales (Telegram, Email, Logs) de forma simultánea.
Aísla errores entre adaptadores para que el fallo de uno no impida la ejecución del resto.
"""

from src.core.domain.entities import Convocatoria, EventoCambio, Fuente, NotificacionResult
from src.core.domain.exceptions import NotificationError
from src.core.domain.ports import NotificationPort
from src.infra.logging import get_logger

logger = get_logger(__name__)


class CompositeNotificationAdapter(NotificationPort):
    """
    Implementa el patrón Composite para ejecutar múltiples adaptadores de notificación.
    Garantiza que el fallo de un adaptador no impida la ejecución del resto.
    Captura NotificationError de cada adapter y lo registra como FALLIDO en el resultado.
    """

    def __init__(self, adapters: list[NotificationPort], canal_names: list[str] | None = None) -> None:
        self.adapters = adapters
        self.canal_names = canal_names or [type(a).__name__ for a in adapters]

    async def notify_event(self, evento: EventoCambio, convocatoria: Convocatoria, fuente: Fuente) -> NotificacionResult:
        last_result: NotificacionResult | None = None
        any_sent = False
        any_failed = False
        last_error: str | None = None

        for adapter, canal_name in zip(self.adapters, self.canal_names, strict=True):
            try:
                result = await adapter.notify_event(evento, convocatoria, fuente)
                last_result = result
                if result.estado == "ENVIADO":
                    any_sent = True
                elif result.estado == "FALLIDO":
                    any_failed = True
                    last_error = result.error_log
            except NotificationError as e:
                any_failed = True
                last_error = str(e)
                logger.error(
                    "Adaptador de notificación falló, continuando con el resto",
                    canal=canal_name,
                    evento_id=str(evento.id),
                    error=str(e),
                )
                last_result = NotificacionResult(
                    evento_id=evento.id,
                    canal=canal_name.upper(),
                    destinatario="fallo",
                    estado="FALLIDO",
                    error_log=str(e),
                )

        if any_sent and not any_failed:
            return NotificacionResult(
                evento_id=evento.id,
                canal="COMPOSITE",
                destinatario="multiples",
                estado="ENVIADO",
            )
        if any_sent and any_failed:
            return NotificacionResult(
                evento_id=evento.id,
                canal="COMPOSITE",
                destinatario="multiples",
                estado="ENVIADO",
                error_log=f"algunos canales fallaron: {last_error}",
            )
        if any_failed:
            return NotificacionResult(
                evento_id=evento.id,
                canal="COMPOSITE",
                destinatario="multiples",
                estado="FALLIDO",
                error_log=last_error,
            )

        if last_result:
            return last_result

        return NotificacionResult(
            evento_id=evento.id,
            canal="COMPOSITE",
            destinatario="ninguno",
            estado="SKIPPED",
            error_log="no hay adaptadores registrados",
        )
