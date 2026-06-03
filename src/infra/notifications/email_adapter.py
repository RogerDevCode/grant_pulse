"""
Implementación del adaptador de notificaciones para Email usando SMTP asíncrono.
"""

from email.message import EmailMessage

import aiosmtplib

from src.core.domain.entities import Convocatoria, EventoCambio, Fuente, NotificacionResult
from src.core.domain.exceptions import NotificationError
from src.core.domain.ports import NotificationPort
from src.infra.logging import get_logger

logger = get_logger(__name__)


class EmailNotificationAdapter(NotificationPort):
    """
    Envía alertas por correo electrónico mediante un servidor SMTP.
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        from_email: str,
        target_emails: list[str],
        use_tls: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.from_email = from_email
        self.target_emails = target_emails
        self.use_tls = use_tls

    async def notify_event(self, evento: EventoCambio, convocatoria: Convocatoria, fuente: Fuente) -> NotificacionResult:
        dest = ", ".join(self.target_emails) if self.target_emails else "no_configurado"

        if not self.host or not self.target_emails:
            logger.warning("Email no configurado. Saltando notificación.", fuente=fuente.nombre)
            return NotificacionResult(
                evento_id=evento.id,
                canal="EMAIL",
                destinatario=dest,
                estado="SKIPPED",
                error_log="host o target_emails no configurados",
            )

        if not evento.es_relevante:
            return NotificacionResult(
                evento_id=evento.id,
                canal="EMAIL",
                destinatario=dest,
                estado="SKIPPED",
                error_log="evento no relevante",
            )

        asunto = f"GrantPulse: {evento.tipo} en {fuente.nombre}"
        cuerpo = self._format_body(evento, convocatoria, fuente)

        msg = EmailMessage()
        msg["Subject"] = asunto
        msg["From"] = self.from_email
        msg["To"] = ", ".join(self.target_emails)
        msg.set_content(cuerpo)

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                use_tls=self.use_tls,
            )
            logger.info("Notificación por Email enviada exitosamente", fuente=fuente.nombre)
            return NotificacionResult(
                evento_id=evento.id,
                canal="EMAIL",
                destinatario=dest,
                estado="ENVIADO",
            )
        except Exception as e:
            msg_err = f"Error enviando email via {self.host}: {e}"
            logger.error(msg_err, exc=e)
            raise NotificationError(msg_err) from e

    def _format_body(self, evento: EventoCambio, convocatoria: Convocatoria, fuente: Fuente) -> str:
        """Formatea el cuerpo del correo en texto plano."""
        if evento.tipo == "APERTURA":
            content = (
                f"NUEVA CONVOCATORIA DETECTADA\n"
                f"---------------------------\n"
                f"Fuente: {fuente.nombre}\n"
                f"Título: {convocatoria.titulo}\n"
                f"Monto: {convocatoria.monto or 'No definido'}\n"
                f"Cierre: {convocatoria.fecha_cierre or 'No definido'}\n"
                f"Estado: {convocatoria.estado}\n"
            )
        else:
            cambios = [f"- {d.campo}: '{d.valor_anterior}' -> '{d.valor_nuevo}'" for d in evento.deltas]
            content = (
                f"CAMBIO RELEVANTE DETECTADO\n"
                f"--------------------------\n"
                f"Fuente: {fuente.nombre}\n"
                f"Título: {convocatoria.titulo}\n"
                f"Cambios detectados:\n" + "\n".join(cambios) + "\n"
            )

        footer = f"\nEnlace al detalle: {convocatoria.url_detalle}\n\nEste es un mensaje automático de GrantPulse."
        return content + footer
