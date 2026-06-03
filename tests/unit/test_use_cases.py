"""
Tests unitarios para el caso de uso central de monitoreo.
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
    RulesConfig,
    SelectorConfig,
    Snapshot,
)
from src.core.domain.exceptions import NetworkError
from src.core.domain.ports import ConvocatoriaRepository, ScraperPort, SnapshotRepository


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
    def __init__(self, existing: list[Convocatoria]):
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

    async def save_evento_cambio(self, evento: EventoCambio, snapshot_id: UUID) -> EventoCambio: # noqa: ARG002
        self.saved_eventos.append(evento)
        return evento

    async def flush(self) -> None:
        pass


@pytest.fixture
def mock_fuente_uc() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="Fuente Test UC",
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
async def test_monitoreo_flujo_feliz_con_cambios(mock_fuente_uc: Fuente) -> None:
    # Preparar estado anterior
    antigua = Convocatoria(
        fuente_id=mock_fuente_uc.id,
        identificador_externo="EXT01",
        titulo="Viejo",
        url_detalle="https://test.com/1",  # type: ignore
        estado="ABIERTO",
    )
    repo_convs = MockConvocatoriaRepository(existing=[antigua])
    repo_snaps = MockSnapshotRepository()

    # Preparar el input extraído (1 existente modificado, 1 nuevo)
    raw_items: list[dict[str, str | None]] = [
        {
            "identificador": "EXT01",
            "titulo": "Viejo",
            "url_detalle": "/1",
            "estado": "CERRADO",  # Cambio de estado!
        },
        {"identificador": "EXT02", "titulo": "Nuevo Fondo", "url_detalle": "/2", "estado": "ABIERTO"},
    ]
    scraper = MockScraper(raw_items)

    uc = MonitoreoUseCase(scraper, repo_snaps, repo_convs)

    # Ejecutar
    eventos = await uc.ejecutar_monitoreo(mock_fuente_uc)

    # Validar
    assert len(eventos) == 2

    eventos_dict = {e.tipo: e for e in eventos}
    assert "APERTURA" in eventos_dict
    assert "MODIFICACION" in eventos_dict

    # Validar persistencia
    assert len(repo_snaps.saved) == 1
    assert len(repo_convs.saved_convocatorias) == 2  # Se guardaron/upsert ambas
    assert len(repo_convs.saved_eventos) == 2


@pytest.mark.asyncio
async def test_monitoreo_falla_rapido_en_red(mock_fuente_uc: Fuente) -> None:
    scraper = MockScraper([], raise_on_fetch=True)
    repo_convs = MockConvocatoriaRepository(existing=[])
    repo_snaps = MockSnapshotRepository()

    uc = MonitoreoUseCase(scraper, repo_snaps, repo_convs)

    with pytest.raises(NetworkError):
        await uc.ejecutar_monitoreo(mock_fuente_uc)

    # Nada se debe haber guardado
    assert len(repo_snaps.saved) == 0
    assert len(repo_convs.saved_convocatorias) == 0
