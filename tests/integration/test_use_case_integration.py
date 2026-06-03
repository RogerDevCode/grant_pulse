"""
Tests de integración para el caso de uso de monitoreo.
Valida el flujo completo: scrape → normalize → detect_changes → persist → notify → persist_notif.
Usa mocks para scraper y repos, pero prueba la orquestación real del use case.
"""

from typing import Any
from uuid import UUID, uuid4

import pytest

from src.core.application.use_cases import MonitoreoUseCase
from src.core.domain.entities import (
    AlertsConfig,
    Convocatoria,
    EventoCambio,
    Fuente,
    NotificacionResult,
    RulesConfig,
    SelectorConfig,
    Snapshot,
)
from src.core.domain.exceptions import NetworkError, NotificationError
from src.core.domain.ports import (
    ConvocatoriaRepository,
    NotificacionRepository,
    NotificationPort,
    ScraperPort,
    SnapshotRepository,
)


class MockScraper(ScraperPort):
    def __init__(self, raw_items: list[dict[str, Any]], raise_on_fetch: bool = False):
        self.raw_items = raw_items
        self.raise_on_fetch = raise_on_fetch

    async def fetch(self, fuente: Fuente) -> Snapshot:
        if self.raise_on_fetch:
            raise NetworkError("Fallo de red simulado")
        return Snapshot(
            fuente_id=fuente.id, contenido_crudo="<html>mock</html>", hash_contenido="123", estado_ejecucion="SUCCESS"
        )

    async def extract(self, snapshot: Snapshot, fuente: Fuente) -> list[dict[str, str | None]]:  # noqa: ARG002
        return self.raw_items


class MockSnapshotRepository(SnapshotRepository):
    def __init__(self) -> None:
        self.saved: list[Snapshot] = []

    async def save(self, snapshot: Snapshot) -> Snapshot:
        self.saved.append(snapshot)
        return snapshot

    async def get_latest_by_fuente(self, fuente_id: UUID) -> Snapshot | None:  # noqa: ARG002
        return self.saved[-1] if self.saved else None


class MockConvocatoriaRepository(ConvocatoriaRepository):
    def __init__(self, existing: list[Convocatoria]) -> None:
        self.existing = existing
        self.saved_convocatorias: list[Convocatoria] = []
        self.saved_eventos: list[EventoCambio] = []

    async def get_by_fuente_and_externo(self, fuente_id: UUID, identificador_externo: str) -> Convocatoria | None:
        for c in self.existing:
            if c.fuente_id == fuente_id and c.identificador_externo == identificador_externo:
                return c
        return None

    async def get_all_by_fuente(self, fuente_id: UUID) -> list[Convocatoria]:
        return [c for c in self.existing if c.fuente_id == fuente_id]

    async def save(self, convocatoria: Convocatoria) -> Convocatoria:
        self.saved_convocatorias.append(convocatoria)
        return convocatoria

    async def save_evento_cambio(self, evento: EventoCambio, snapshot_id: UUID) -> EventoCambio:  # noqa: ARG002
        self.saved_eventos.append(evento)
        return evento

    async def flush(self) -> None:
        pass


class MockNotificacionRepository(NotificacionRepository):
    def __init__(self, fail: bool = False) -> None:
        self.saved: list[NotificacionResult] = []
        self.fail = fail

    async def save(self, resultado: NotificacionResult) -> NotificacionResult:
        if self.fail:
            raise RuntimeError("DB connection lost")
        self.saved.append(resultado)
        return resultado


class MockNotifier(NotificationPort):
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[EventoCambio, Convocatoria, Fuente]] = []

    async def notify_event(self, evento: EventoCambio, convocatoria: Convocatoria, fuente: Fuente) -> NotificacionResult:
        if self.fail:
            raise NotificationError("Notifier configured wrong")
        self.calls.append((evento, convocatoria, fuente))
        return NotificacionResult(
            evento_id=evento.id,
            canal="MOCK",
            destinatario="test@test.com",
            estado="ENVIADO",
        )


@pytest.fixture
def mock_fuente() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="Fuente Integration",
        url_base="https://test.com",  # type: ignore
        configuracion_reglas=RulesConfig(
            nombre="test",
            url_busqueda="https://test.com/fondos",  # type: ignore
            selectores=SelectorConfig(
                contenedor_items="div", identificador="id", titulo="t", descripcion="d", link_detalle="l", estado="e"
            ),
            alertas=AlertsConfig(campos_sensibles=["estado"]),
        ),
    )


@pytest.mark.asyncio
async def test_full_pipeline_with_notifications(mock_fuente: Fuente) -> None:
    antigua = Convocatoria(
        fuente_id=mock_fuente.id,
        identificador_externo="EXT01",
        titulo="Existente",
        url_detalle="https://test.com/1",  # type: ignore
        estado="ABIERTO",
    )
    repo_convs = MockConvocatoriaRepository(existing=[antigua])
    repo_snaps = MockSnapshotRepository()
    repo_notif = MockNotificacionRepository()
    notifier = MockNotifier()

    raw_items: list[dict[str, str | None]] = [
        {"identificador": "EXT01", "titulo": "Existente", "url_detalle": "/1", "estado": "CERRADO"},
        {"identificador": "EXT02", "titulo": "Nueva", "url_detalle": "/2", "estado": "ABIERTO"},
    ]
    scraper = MockScraper(raw_items)

    uc = MonitoreoUseCase(
        scraper=scraper,
        snapshot_repo=repo_snaps,
        convocatoria_repo=repo_convs,
        notifier=notifier,
        notificacion_repo=repo_notif,
    )

    eventos = await uc.ejecutar_monitoreo(mock_fuente)

    assert len(eventos) == 2
    assert len(repo_snaps.saved) == 1
    assert len(repo_convs.saved_convocatorias) == 2
    assert len(repo_convs.saved_eventos) == 2
    assert len(notifier.calls) == 2
    assert len(repo_notif.saved) == 2
    assert all(r.estado == "ENVIADO" for r in repo_notif.saved)


@pytest.mark.asyncio
async def test_notification_error_creates_fallback_result(mock_fuente: Fuente) -> None:
    antigua = Convocatoria(
        fuente_id=mock_fuente.id,
        identificador_externo="EXT01",
        titulo="Existente",
        url_detalle="https://test.com/1",  # type: ignore
        estado="ABIERTO",
    )
    repo_convs = MockConvocatoriaRepository(existing=[antigua])
    repo_snaps = MockSnapshotRepository()
    repo_notif = MockNotificacionRepository()
    notifier = MockNotifier(fail=True)

    raw_items: list[dict[str, str | None]] = [
        {"identificador": "EXT01", "titulo": "Existente", "url_detalle": "/1", "estado": "CERRADO"},
    ]
    scraper = MockScraper(raw_items)

    uc = MonitoreoUseCase(
        scraper=scraper,
        snapshot_repo=repo_snaps,
        convocatoria_repo=repo_convs,
        notifier=notifier,
        notificacion_repo=repo_notif,
    )

    eventos = await uc.ejecutar_monitoreo(mock_fuente)

    assert len(eventos) == 1
    assert len(repo_notif.saved) == 1
    assert repo_notif.saved[0].estado == "FALLIDO"
    assert repo_notif.saved[0].canal == "UNKNOWN"
    assert "Notifier configured wrong" in (repo_notif.saved[0].error_log or "")


@pytest.mark.asyncio
async def test_notificacion_persistence_error_tracked(mock_fuente: Fuente) -> None:
    antigua = Convocatoria(
        fuente_id=mock_fuente.id,
        identificador_externo="EXT01",
        titulo="Existente",
        url_detalle="https://test.com/1",  # type: ignore
        estado="ABIERTO",
    )
    repo_convs = MockConvocatoriaRepository(existing=[antigua])
    repo_snaps = MockSnapshotRepository()
    repo_notif = MockNotificacionRepository(fail=True)
    notifier = MockNotifier()

    raw_items: list[dict[str, str | None]] = [
        {"identificador": "EXT01", "titulo": "Existente", "url_detalle": "/1", "estado": "CERRADO"},
    ]
    scraper = MockScraper(raw_items)

    uc = MonitoreoUseCase(
        scraper=scraper,
        snapshot_repo=repo_snaps,
        convocatoria_repo=repo_convs,
        notifier=notifier,
        notificacion_repo=repo_notif,
    )

    eventos = await uc.ejecutar_monitoreo(mock_fuente)

    assert len(eventos) == 1
    assert len(notifier.calls) == 1
    assert len(repo_notif.saved) == 0


@pytest.mark.asyncio
async def test_no_notifier_means_no_notifications(mock_fuente: Fuente) -> None:
    repo_convs = MockConvocatoriaRepository(existing=[])
    repo_snaps = MockSnapshotRepository()

    raw_items: list[dict[str, str | None]] = [
        {"identificador": "EXT01", "titulo": "Nueva", "url_detalle": "/1", "estado": "ABIERTO"},
    ]
    scraper = MockScraper(raw_items)

    uc = MonitoreoUseCase(
        scraper=scraper,
        snapshot_repo=repo_snaps,
        convocatoria_repo=repo_convs,
        notifier=None,
        notificacion_repo=None,
    )

    eventos = await uc.ejecutar_monitoreo(mock_fuente)

    assert len(eventos) == 1
    assert eventos[0].tipo == "APERTURA"


@pytest.mark.asyncio
async def test_deduplication_by_identificador_externo(mock_fuente: Fuente) -> None:
    repo_convs = MockConvocatoriaRepository(existing=[])
    repo_snaps = MockSnapshotRepository()

    raw_items: list[dict[str, str | None]] = [
        {"identificador": "DUP1", "titulo": "Primera version", "url_detalle": "/1", "estado": "ABIERTO"},
        {"identificador": "DUP1", "titulo": "Segunda version", "url_detalle": "/1b", "estado": "ABIERTO"},
        {"identificador": "UNIQUE", "titulo": "Unica", "url_detalle": "/2", "estado": "ABIERTO"},
    ]
    scraper = MockScraper(raw_items)

    uc = MonitoreoUseCase(
        scraper=scraper,
        snapshot_repo=repo_snaps,
        convocatoria_repo=repo_convs,
    )

    await uc.ejecutar_monitoreo(mock_fuente)

    deduped_ids = {c.identificador_externo for c in repo_convs.saved_convocatorias}
    assert deduped_ids == {"DUP1", "UNIQUE"}
    assert len(repo_convs.saved_convocatorias) == 2
    dup1 = [c for c in repo_convs.saved_convocatorias if c.identificador_externo == "DUP1"][0]
    assert dup1.titulo == "Segunda version"


@pytest.mark.asyncio
async def test_only_relevant_events_get_notified(mock_fuente: Fuente) -> None:
    antigua = Convocatoria(
        fuente_id=mock_fuente.id,
        identificador_externo="EXT01",
        titulo="Existente",
        url_detalle="https://test.com/1",  # type: ignore
        estado="ABIERTO",
    )
    repo_convs = MockConvocatoriaRepository(existing=[antigua])
    repo_snaps = MockSnapshotRepository()
    notifier = MockNotifier()

    raw_items: list[dict[str, str | None]] = [
        {"identificador": "EXT01", "titulo": "Titulo cambiado", "url_detalle": "/1", "estado": "ABIERTO"},
    ]
    scraper = MockScraper(raw_items)

    uc = MonitoreoUseCase(
        scraper=scraper,
        snapshot_repo=repo_snaps,
        convocatoria_repo=repo_convs,
        notifier=notifier,
    )

    eventos = await uc.ejecutar_monitoreo(mock_fuente)

    assert len(eventos) == 1
    assert eventos[0].tipo == "MODIFICACION"
    assert eventos[0].es_relevante is False
    assert len(notifier.calls) == 0


@pytest.mark.asyncio
async def test_zero_eventos_no_notification_loop(mock_fuente: Fuente) -> None:
    antigua = Convocatoria(
        fuente_id=mock_fuente.id,
        identificador_externo="EXT01",
        titulo="Igual",
        url_detalle="https://test.com/1",  # type: ignore
        estado="ABIERTO",
    )
    repo_convs = MockConvocatoriaRepository(existing=[antigua])
    repo_snaps = MockSnapshotRepository()
    notifier = MockNotifier()

    raw_items: list[dict[str, str | None]] = [
        {"identificador": "EXT01", "titulo": "Igual", "url_detalle": "/1", "estado": "ABIERTO"},
    ]
    scraper = MockScraper(raw_items)

    uc = MonitoreoUseCase(
        scraper=scraper,
        snapshot_repo=repo_snaps,
        convocatoria_repo=repo_convs,
        notifier=notifier,
    )

    eventos = await uc.ejecutar_monitoreo(mock_fuente)

    assert len(eventos) == 0
    assert len(notifier.calls) == 0


@pytest.mark.asyncio
async def test_network_error_propagates_as_grant_pulse_error(mock_fuente: Fuente) -> None:
    repo_convs = MockConvocatoriaRepository(existing=[])
    repo_snaps = MockSnapshotRepository()

    scraper = MockScraper([], raise_on_fetch=True)

    uc = MonitoreoUseCase(
        scraper=scraper,
        snapshot_repo=repo_snaps,
        convocatoria_repo=repo_convs,
    )

    with pytest.raises(NetworkError):
        await uc.ejecutar_monitoreo(mock_fuente)

    assert len(repo_snaps.saved) == 0
    assert len(repo_convs.saved_convocatorias) == 0
