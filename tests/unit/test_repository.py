"""
Tests unitarios para los repositorios SQLAlchemy usando mocks de sesión asíncrona.
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.domain.entities import Convocatoria, Fuente, RulesConfig, SelectorConfig
from src.core.domain.exceptions import PersistenceError
from src.infra.db.models import ConvocatoriaORM, FuenteORM
from src.infra.db.repository import SQLConvocatoriaRepository, SQLFuenteRepository


@pytest.fixture
def mock_session() -> AsyncSession:
    return AsyncMock(spec=AsyncSession)


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
def dummy_fuente_orm(dummy_fuente: Fuente) -> FuenteORM:
    return FuenteORM(
        id=dummy_fuente.id,
        nombre=dummy_fuente.nombre,
        url_base=str(dummy_fuente.url_base),
        configuracion_yaml=dummy_fuente.configuracion_reglas.model_dump_json(),
        activa=dummy_fuente.activa,
        creado_en=dummy_fuente.creado_en,
        actualizado_en=dummy_fuente.actualizado_en,
    )


@pytest.mark.asyncio
async def test_fuente_repository_get_by_id_success(mock_session: Any, dummy_fuente_orm: FuenteORM) -> None:
    # Setup mock: get_by_id usa session.get(), no execute()
    mock_session.get.return_value = dummy_fuente_orm

    repo = SQLFuenteRepository(mock_session)
    fuente = await repo.get_by_id(dummy_fuente_orm.id)

    assert fuente is not None
    assert fuente.id == dummy_fuente_orm.id
    assert fuente.nombre == "Fuente Test"
    mock_session.get.assert_called_once_with(FuenteORM, dummy_fuente_orm.id)


@pytest.mark.asyncio
async def test_fuente_repository_get_by_id_db_error(mock_session: Any) -> None:
    mock_session.get.side_effect = SQLAlchemyError("DB Down")
    repo = SQLFuenteRepository(mock_session)

    with pytest.raises(PersistenceError, match=r"(?i)error al consultar fuente"):
        await repo.get_by_id(999)


@pytest.mark.asyncio
async def test_convocatoria_repository_save_insert(mock_session: Any, dummy_fuente: Fuente) -> None:
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute.return_value = mock_result

    conv = Convocatoria(
        fuente_id=dummy_fuente.id,
        identificador_externo="EXT-123",
        titulo="Test",
        url_detalle="https://test.com/123",  # type: ignore
        regiones=["Metropolitana"],
        estado="ABIERTO",
    )

    repo = SQLConvocatoriaRepository(mock_session)
    result = await repo.save(conv)

    assert result.identificador_externo == "EXT-123"
    assert result.regiones == ["Metropolitana"]
    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()

    added_orm = mock_session.add.call_args[0][0]
    assert isinstance(added_orm, ConvocatoriaORM)
    assert added_orm.regiones == ["Metropolitana"]


@pytest.mark.asyncio
async def test_convocatoria_repository_save_update(mock_session: Any, dummy_fuente: Fuente) -> None:
    # Setup: existing conv found
    existing_orm = ConvocatoriaORM(
        id=1,
        fuente_id=dummy_fuente.id,
        identificador_externo="EXT-123",
        titulo="Viejo",
        url_detail="https://test.com/123",
        estado="ABIERTO",
        creado_en=datetime.now(UTC),
        actualizado_en=datetime.now(UTC),
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = existing_orm
    mock_session.execute.return_value = mock_result

    # Nueva info
    conv = Convocatoria(
        id=existing_orm.id,
        fuente_id=dummy_fuente.id,
        identificador_externo="EXT-123",
        titulo="Nuevo Titulo",
        url_detalle="https://test.com/123",  # type: ignore
        regiones=["O'Higgins"],
        estado="CERRADO",
    )

    repo = SQLConvocatoriaRepository(mock_session)
    result = await repo.save(conv)

    # Verificamos que se actualizó el ORM existente
    assert result.titulo == "Nuevo Titulo"
    assert result.regiones == ["O'Higgins"]
    assert existing_orm.titulo == "Nuevo Titulo"
    assert existing_orm.estado == "CERRADO"
    assert existing_orm.regiones == ["O'Higgins"]

    mock_session.add.assert_not_called()  # Fue un update
    mock_session.flush.assert_called_once()
