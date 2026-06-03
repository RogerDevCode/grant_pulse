"""
Tests unitarios rápidos para las rutas de la API.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.infra.db.connection import get_db_session
from src.presentation.api.main import app


# Mock sencillo del generador de sesión para que no intente conectar a DB
async def mock_get_db_session() -> AsyncGenerator[Any]:
    yield None


app.dependency_overrides[get_db_session] = mock_get_db_session

client = TestClient(app)


def test_list_convocatorias_db_error() -> None:
    # Como la DB de verdad no está inyectada en el test de integración completo aquí,
    # y la DB mockeada es un `None`, FastAPI fallará al intentar llamar a session.execute(query).
    # Solo validaremos que la API levanta y da error 500 por la falla de DB o algo similar,
    # comprobando el cableado base de la ruta.

    with pytest.raises(AttributeError):
        client.get("/api/v1/convocatorias")  # pyright: ignore[reportUnknownMemberType]
