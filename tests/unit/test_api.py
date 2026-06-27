"""Tests unitarios rápidos para las rutas de la API."""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.infra.db.connection import get_db_session
from src.presentation.api import main as api_main

app = api_main.app


# Mock sencillo del generador de sesión para que no intente conectar a DB
async def mock_get_db_session() -> AsyncGenerator[Any]:
    yield None


app.dependency_overrides[get_db_session] = mock_get_db_session


@pytest.mark.asyncio
async def test_list_convocatorias_db_error() -> None:
    # La DB real está reemplazada por `None`, así que la ruta debe fallar al intentar usarla.
    # Validamos que el cableado de la API sigue exponiendo el error y no lo oculta.

    with patch("src.infra.cli.sync_all_rules", new=AsyncMock(return_value=None)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with pytest.raises(AttributeError):
                await client.get("/api/v1/convocatorias")


def test_run_configures_uvicorn_to_log_to_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "9010")

    captured: dict[str, Any] = {}

    def _fake_run(*_args: Any, **kwargs: Any) -> None:
        captured.update(kwargs)

    with patch("uvicorn.run", side_effect=_fake_run):
        api_main.run()

    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9010
    assert captured["log_level"] == "info"

    log_config = captured["log_config"]
    assert log_config["handlers"]["default"]["stream"] == "ext://sys.stdout"
    assert log_config["handlers"]["access"]["stream"] == "ext://sys.stdout"


@pytest.mark.asyncio
async def test_list_fuentes_success() -> None:
    from unittest.mock import MagicMock
    from datetime import datetime, UTC
    from src.infra.db.models import FuenteORM

    mock_fuente = FuenteORM(
        id=1,
        nombre="Test Fuente",
        url_base="https://test.com",
        configuracion_yaml="nombre: Test Fuente",
        activa=True,
        creado_en=datetime.now(UTC),
        actualizado_en=datetime.now(UTC),
    )

    mock_execute_res = MagicMock()
    mock_execute_res.scalars.return_value.all.return_value = [mock_fuente]
    
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_execute_res

    async def temp_mock_db_session() -> AsyncGenerator[Any]:
        yield mock_session

    app.dependency_overrides[get_db_session] = temp_mock_db_session
    try:
        with patch("src.infra.cli.sync_all_rules", new=AsyncMock(return_value=None)):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/v1/fuentes")
                assert response.status_code == 200
                data = response.json()
                assert len(data) == 1
                assert data[0]["nombre"] == "Test Fuente"
                assert data[0]["url_base"] == "https://test.com"
    finally:
        app.dependency_overrides[get_db_session] = mock_get_db_session


@pytest.mark.asyncio
async def test_get_dashboard_stats_success() -> None:
    from unittest.mock import MagicMock

    mock_execute_res1 = MagicMock()
    mock_execute_res1.scalar.return_value = 10
    
    mock_execute_res2 = MagicMock()
    mock_execute_res2.scalar.return_value = 5
    
    mock_execute_res3 = MagicMock()
    mock_execute_res3.scalar.return_value = 2

    mock_session = AsyncMock()
    mock_session.execute.side_effect = [mock_execute_res1, mock_execute_res2, mock_execute_res3]

    async def temp_mock_db_session() -> AsyncGenerator[Any]:
        yield mock_session

    app.dependency_overrides[get_db_session] = temp_mock_db_session
    try:
        with patch("src.infra.cli.sync_all_rules", new=AsyncMock(return_value=None)):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/v1/dashboard")
                assert response.status_code == 200
                data = response.json()
                assert data["total_convocatorias"] == 10
                assert data["convocatorias_activas"] == 5
                assert data["total_fuentes"] == 2
    finally:
        app.dependency_overrides[get_db_session] = mock_get_db_session


@pytest.mark.asyncio
async def test_get_scrape_status_success() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/scrape/status")
        assert response.status_code == 200
        data = response.json()
        assert "en_curso" in data
