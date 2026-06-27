"""
Implementación del adaptador de notificaciones para Telegram.
"""

import httpx

from src.core.domain.entities import Convocatoria, EventoCambio, Fuente, NotificacionResult
from src.core.domain.exceptions import NotificationError
from src.core.domain.ports import NotificationPort
from src.infra.config import settings
from src.infra.logging import get_logger

logger = get_logger(__name__)


class TelegramNotificationAdapter(NotificationPort):
    """
    Envía alertas a un chat de Telegram usando un bot.
    Utiliza parse_mode='HTML' para mejorar la legibilidad.
    """

    def __init__(self, bot_token: str | None = None, chat_id: str | None = None) -> None:
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or settings.TELEGRAM_CHAT_ID
        self.api_url = (
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            if self.bot_token
            else ""
            if self.bot_token
            else ""
        )

    async def notify_event(
        self, evento: EventoCambio, convocatoria: Convocatoria, fuente: Fuente
    ) -> NotificacionResult:
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram no configurado. Saltando notificación.", fuente=fuente.nombre)
            return NotificacionResult(
                evento_id=evento.id,
                canal="TELEGRAM",
                destinatario="no_configurado",
                estado="SKIPPED",
                error_log="bot_token o chat_id no configurados",
            )

        if not evento.es_relevante:
            return NotificacionResult(
                evento_id=evento.id,
                canal="TELEGRAM",
                destinatario=self.chat_id,
                estado="SKIPPED",
                error_log="evento no relevante",
            )

        mensaje = self._format_message(evento, convocatoria, fuente)

        import asyncio
        max_retries = 3
        backoff = 1.0

        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.post(
                        self.api_url,
                        json={
                            "chat_id": self.chat_id,
                            "text": mensaje,
                            "parse_mode": "HTML",
                            "disable_web_page_preview": False,
                        },
                    )
                    response.raise_for_status()
                    logger.info("Notificación Telegram enviada exitosamente", fuente=fuente.nombre)
                    return NotificacionResult(
                        evento_id=evento.id,
                        canal="TELEGRAM",
                        destinatario=self.chat_id,
                        estado="ENVIADO",
                    )
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                # Si es un error de autenticación/malformación (400, 401, 403), no reintentar
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code in {400, 401, 403}:
                    msg = f"Error de Telegram API ({e.response.status_code}): {e.response.text}"
                    logger.error(msg, exc=e)
                    raise NotificationError(msg) from e

                if attempt == max_retries:
                    msg = f"Error de red/API final para Telegram tras {max_retries} intentos: {e}"
                    logger.error(msg, exc=e)
                    raise NotificationError(msg) from e

                delay = backoff * (2 ** (attempt - 1))
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
                    retry_after = e.response.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        delay = float(retry_after)

                logger.warning(
                    f"Intento {attempt} fallido para Telegram. Reintentando en {delay:.1f}s...",
                    fuente=fuente.nombre,
                    exc=e,
                )
                await asyncio.sleep(delay)

        raise NotificationError("Error inesperado en loop de reintentos Telegram")

    def _format_message(self, evento: EventoCambio, convocatoria: Convocatoria, fuente: Fuente) -> str:
        """Formatea el mensaje usando etiquetas HTML soportadas por Telegram."""
        if evento.tipo == "APERTURA":
            header = f"<b>🆕 NUEVA CONVOCATORIA</b>\n🏛 <i>{fuente.nombre}</i>"
            body = (
                f"\n\n<b>{convocatoria.titulo}</b>"
                f"\n\n💰 Monto: {self._format_currency(convocatoria.monto)}"
                f"\n📅 Cierre: {convocatoria.fecha_cierre.strftime('%d/%m/%Y') if convocatoria.fecha_cierre else 'No definido'}"
            )
        else:
            header = f"<b>⚠️ CAMBIO DETECTADO</b>\n🏛 <i>{fuente.nombre}</i>"
            cambios: list[str] = []
            for d in evento.deltas:
                cambios.append(
                    f"• <b>{d.campo}:</b> <strike>{d.valor_anterior or 'N/A'}</strike> → {d.valor_nuevo or 'N/A'}"
                )

            body = f"\n\n<b>{convocatoria.titulo}</b>\n\n" + "\n".join(cambios)
        footer = f"\n\n🔗 <a href='{convocatoria.url_detalle}'>Ver detalle en el portal</a>"
        return header + body + footer

    def _format_currency(self, val: float | None) -> str:
        if val is None:
            return "No definido"
        return f"${val:,.0f}".replace(",", ".")
