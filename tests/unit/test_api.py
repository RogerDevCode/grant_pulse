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

    with patch.object(api_main, "_ensure_startup_schema", new=AsyncMock(return_value=None)), patch(
        "src.infra.cli.sync_all_rules", new=AsyncMock(return_value=None)
    ):
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
