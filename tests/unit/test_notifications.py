"""
Tests unitarios para la capa de notificaciones.
"""

import logging
import httpx
from unittest.mock import MagicMock, patch

import pytest

from src.core.domain.entities import (
    Convocatoria,
    Delta,
    EventoCambio,
    Fuente,
    NotificacionResult,
    RulesConfig,
    SelectorConfig,
)
from src.core.domain.exceptions import NotificationError
from src.core.domain.ports import NotificationPort
from src.infra.notifications.composite_adapter import CompositeNotificationAdapter
from src.infra.notifications.logger_adapter import LoggerNotificationAdapter


@pytest.fixture
def dummy_fuente() -> Fuente:
    return Fuente(
        id=1,
        nombre="Fuente Test",
        url_base="https://test.com",  # type: ignore
        configuracion_reglas=RulesConfig(
            nombre="test",
            url_busqueda="https://test.com/fondos",  # type: ignore
            selectores=SelectorConfig(
                contenedor_items="div", identificador="id", titulo="t", descripcion="d", link_detalle="l", estado="e"
            ),
        ),
    )


@pytest.fixture
def dummy_convocatoria(dummy_fuente: Fuente) -> Convocatoria:
    return Convocatoria(
        id=1,
        fuente_id=dummy_fuente.id,  # type: ignore[arg-type]
        identificador_externo="123",
        titulo="Fondo Prueba",
        url_detalle="https://test.com/123",  # type: ignore
        estado="ABIERTO",
    )


@pytest.mark.asyncio
async def test_logger_adapter_apertura(
    caplog: pytest.LogCaptureFixture, dummy_fuente: Fuente, dummy_convocatoria: Convocatoria
) -> None:
    caplog.set_level(logging.INFO)

    evento = EventoCambio(id=1, convocatoria_id=dummy_convocatoria.id, tipo="APERTURA", es_relevante=True)

    adapter = LoggerNotificationAdapter()
    result = await adapter.notify_event(evento, dummy_convocatoria, dummy_fuente)

    assert isinstance(result, NotificacionResult)
    assert result.estado == "ENVIADO"
    assert result.canal == "LOGGER"

    record = caplog.records[-1]
    assert record.message == "NOTIFICACION_ENVIADA"

    ctx = getattr(record, "extra_context", {})
    assert ctx.get("tipo") == "APERTURA"
    assert "NUEVA CONVOCATORIA en Fuente Test" in ctx.get("mensaje", "")
    assert "Fondo Prueba" in ctx.get("mensaje", "")


@pytest.mark.asyncio
async def test_logger_adapter_modificacion(
    caplog: pytest.LogCaptureFixture, dummy_fuente: Fuente, dummy_convocatoria: Convocatoria
) -> None:
    caplog.set_level(logging.INFO)

    evento = EventoCambio(
        id=2,
        convocatoria_id=dummy_convocatoria.id,
        tipo="MODIFICACION",
        deltas=[Delta(campo="estado", valor_anterior="ABIERTO", valor_nuevo="CERRADO")],
        es_relevante=True,
    )

    adapter = LoggerNotificationAdapter()
    result = await adapter.notify_event(evento, dummy_convocatoria, dummy_fuente)

    assert isinstance(result, NotificacionResult)
    assert result.estado == "ENVIADO"

    record = caplog.records[-1]
    assert record.message == "NOTIFICACION_ENVIADA"

    ctx = getattr(record, "extra_context", {})
    assert ctx.get("tipo") == "MODIFICACION"
    assert "CAMBIO RELEVANTE en Fuente Test" in ctx.get("mensaje", "")
    assert "estado: 'ABIERTO' -> 'CERRADO'" in ctx.get("mensaje", "")


@pytest.mark.asyncio
async def test_logger_adapter_skips_no_relevantes(
    dummy_fuente: Fuente, dummy_convocatoria: Convocatoria
) -> None:
    evento = EventoCambio(
        id=3,
        convocatoria_id=dummy_convocatoria.id,
        tipo="MODIFICACION",
        deltas=[Delta(campo="url_detalle", valor_anterior="a", valor_nuevo="b")],
        es_relevante=False,
    )

    adapter = LoggerNotificationAdapter()
    result = await adapter.notify_event(evento, dummy_convocatoria, dummy_fuente)

    assert result.estado == "SKIPPED"


@pytest.mark.asyncio
async def test_composite_adapter_collects_results(
    dummy_fuente: Fuente, dummy_convocatoria: Convocatoria
) -> None:
    evento = EventoCambio(id=1, convocatoria_id=dummy_convocatoria.id, tipo="APERTURA", es_relevante=True)

    adapter = CompositeNotificationAdapter(
        adapters=[LoggerNotificationAdapter(), LoggerNotificationAdapter()],
        canal_names=["LOGGER_1", "LOGGER_2"],
    )
    result = await adapter.notify_event(evento, dummy_convocatoria, dummy_fuente)

    assert isinstance(result, NotificacionResult)
    assert result.estado == "ENVIADO"
    assert result.canal == "COMPOSITE"


class FailingAdapter(NotificationPort):
    async def notify_event(self, evento: EventoCambio, convocatoria: Convocatoria, fuente: Fuente) -> NotificacionResult:  # noqa: ARG002
        raise NotificationError("fallo deliberado")


@pytest.mark.asyncio
async def test_composite_adapter_isolates_failures(
    dummy_fuente: Fuente, dummy_convocatoria: Convocatoria
) -> None:
    evento = EventoCambio(id=1, convocatoria_id=dummy_convocatoria.id, tipo="APERTURA", es_relevante=True)

    adapter = CompositeNotificationAdapter(
        adapters=[FailingAdapter(), LoggerNotificationAdapter()],
        canal_names=["FAIL", "LOGGER"],
    )
    result = await adapter.notify_event(evento, dummy_convocatoria, dummy_fuente)

    assert isinstance(result, NotificacionResult)
    assert result.estado == "ENVIADO"
    assert result.error_log is not None
    assert "fallo deliberado" in result.error_log


@pytest.mark.asyncio
async def test_composite_adapter_all_fail(
    dummy_fuente: Fuente, dummy_convocatoria: Convocatoria
) -> None:
    evento = EventoCambio(id=1, convocatoria_id=dummy_convocatoria.id, tipo="APERTURA", es_relevante=True)

    adapter = CompositeNotificationAdapter(
        adapters=[FailingAdapter(), FailingAdapter()],
        canal_names=["FAIL_1", "FAIL_2"],
    )
    result = await adapter.notify_event(evento, dummy_convocatoria, dummy_fuente)

    assert result.estado == "FALLIDO"


@pytest.mark.asyncio
async def test_telegram_adapter_skipped_when_unconfigured(
    dummy_fuente: Fuente, dummy_convocatoria: Convocatoria, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.infra.config import settings
    from src.infra.notifications.telegram_adapter import TelegramNotificationAdapter

    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "")

    evento = EventoCambio(id=1, convocatoria_id=dummy_convocatoria.id, tipo="APERTURA", es_relevante=True)

    adapter = TelegramNotificationAdapter(bot_token="", chat_id="")
    result = await adapter.notify_event(evento, dummy_convocatoria, dummy_fuente)

    assert result.estado == "SKIPPED"
    assert result.canal == "TELEGRAM"


@pytest.mark.asyncio
async def test_notificacion_result_entity() -> None:
    result = NotificacionResult(
        evento_id=1,
        canal="TELEGRAM",
        destinatario="12345",
        estado="ENVIADO",
    )
    assert result.error_log is None

    result_fail = NotificacionResult(
        evento_id=1,
        canal="EMAIL",
        destinatario="a@b.com",
        estado="FALLIDO",
        error_log="timeout",
    )
    assert result_fail.error_log == "timeout"


@pytest.mark.asyncio
async def test_telegram_adapter_retry_success(dummy_fuente: Fuente, dummy_convocatoria: Convocatoria) -> None:
    from unittest.mock import AsyncMock
    from src.infra.notifications.telegram_adapter import TelegramNotificationAdapter

    evento = EventoCambio(id=1, convocatoria_id=dummy_convocatoria.id, tipo="APERTURA", es_relevante=True)
    adapter = TelegramNotificationAdapter(bot_token="test_token", chat_id="test_chat")

    # Mock response classes
    mock_response_ok = MagicMock()
    mock_response_ok.raise_for_status = MagicMock()

    # Mock post calls: first fails with network error, second succeeds
    mock_post = AsyncMock(side_effect=[
        httpx.RequestError("Network glitch"),
        mock_response_ok
    ])

    with patch("httpx.AsyncClient.post", mock_post), patch("asyncio.sleep", AsyncMock()) as mock_sleep:
        res = await adapter.notify_event(evento, dummy_convocatoria, dummy_fuente)
        assert res.estado == "ENVIADO"
        assert mock_post.call_count == 2
        mock_sleep.assert_called_once_with(1.0)


@pytest.mark.asyncio
async def test_telegram_adapter_retry_429_backoff(dummy_fuente: Fuente, dummy_convocatoria: Convocatoria) -> None:
    from unittest.mock import AsyncMock
    from src.infra.notifications.telegram_adapter import TelegramNotificationAdapter

    evento = EventoCambio(id=1, convocatoria_id=dummy_convocatoria.id, tipo="APERTURA", es_relevante=True)
    adapter = TelegramNotificationAdapter(bot_token="test_token", chat_id="test_chat")

    # Mock 429 response with Retry-After header
    mock_response_429 = MagicMock()
    mock_response_429.status_code = 429
    mock_response_429.headers = {"Retry-After": "5"}
    mock_response_429.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError("Too Many Requests", request=MagicMock(), response=mock_response_429))

    mock_response_ok = MagicMock()
    mock_response_ok.raise_for_status = MagicMock()

    mock_post = AsyncMock(side_effect=[
        mock_response_429,
        mock_response_ok
    ])

    with patch("httpx.AsyncClient.post", mock_post), patch("asyncio.sleep", AsyncMock()) as mock_sleep:
        res = await adapter.notify_event(evento, dummy_convocatoria, dummy_fuente)
        assert res.estado == "ENVIADO"
        assert mock_post.call_count == 2
        mock_sleep.assert_called_once_with(5.0)


@pytest.mark.asyncio
async def test_telegram_adapter_retry_fatal_fails_immediately(dummy_fuente: Fuente, dummy_convocatoria: Convocatoria) -> None:
    from unittest.mock import AsyncMock
    from src.infra.notifications.telegram_adapter import TelegramNotificationAdapter
    from typing import Any

    evento = EventoCambio(id=1, convocatoria_id=dummy_convocatoria.id, tipo="APERTURA", es_relevante=True)
    adapter = TelegramNotificationAdapter(bot_token="test_token", chat_id="test_chat")

    mock_response_400 = MagicMock()
    mock_response_400.status_code = 400
    mock_response_400.text = "Bad Request"

    async def side_effect_func(*args: Any, **kwargs: Any) -> Any:
        raise httpx.HTTPStatusError("Bad Request", request=MagicMock(), response=mock_response_400)

    mock_post = AsyncMock(side_effect=side_effect_func)

    with patch("httpx.AsyncClient.post", mock_post), patch("asyncio.sleep", AsyncMock()) as mock_sleep:
        with pytest.raises(NotificationError) as exc_info:
            await adapter.notify_event(evento, dummy_convocatoria, dummy_fuente)
        assert "Error de Telegram API (400)" in str(exc_info.value)
        assert mock_post.call_count == 1
        mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_telegram_adapter_send_message_direct() -> None:
    from unittest.mock import AsyncMock
    from src.infra.notifications.telegram_adapter import TelegramNotificationAdapter

    adapter = TelegramNotificationAdapter(bot_token="test_token", chat_id="test_chat")

    mock_response_ok = MagicMock()
    mock_response_ok.raise_for_status = MagicMock()

    mock_post = AsyncMock(return_value=mock_response_ok)

    with patch("httpx.AsyncClient.post", mock_post):
        res = await adapter.send_message("Hola mundo E2E")
        assert res is True
        assert mock_post.call_count == 1
        call_args = mock_post.call_args[1]
        assert call_args["json"]["text"] == "Hola mundo E2E"
