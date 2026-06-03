"""
Tests unitarios para la capa de notificaciones.
"""

import logging
from uuid import uuid4

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
        id=uuid4(),
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
        fuente_id=dummy_fuente.id,
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

    evento = EventoCambio(convocatoria_id=dummy_convocatoria.id, tipo="APERTURA", es_relevante=True)

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
    evento = EventoCambio(convocatoria_id=dummy_convocatoria.id, tipo="APERTURA", es_relevante=True)

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
    evento = EventoCambio(convocatoria_id=dummy_convocatoria.id, tipo="APERTURA", es_relevante=True)

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
    evento = EventoCambio(convocatoria_id=dummy_convocatoria.id, tipo="APERTURA", es_relevante=True)

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

    evento = EventoCambio(convocatoria_id=dummy_convocatoria.id, tipo="APERTURA", es_relevante=True)

    adapter = TelegramNotificationAdapter(bot_token="", chat_id="")
    result = await adapter.notify_event(evento, dummy_convocatoria, dummy_fuente)

    assert result.estado == "SKIPPED"
    assert result.canal == "TELEGRAM"


@pytest.mark.asyncio
async def test_notificacion_result_entity() -> None:
    result = NotificacionResult(
        evento_id=uuid4(),
        canal="TELEGRAM",
        destinatario="12345",
        estado="ENVIADO",
    )
    assert result.error_log is None

    result_fail = NotificacionResult(
        evento_id=uuid4(),
        canal="EMAIL",
        destinatario="a@b.com",
        estado="FALLIDO",
        error_log="timeout",
    )
    assert result_fail.error_log == "timeout"
