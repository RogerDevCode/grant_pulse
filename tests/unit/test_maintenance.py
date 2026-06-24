from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infra.maintenance import clean_unavailable_convocatorias


@pytest.mark.asyncio
async def test_clean_unavailable_convocatorias_deletes_old_records() -> None:
    # Simulamos que execute devuelve una lista de IDs a borrar
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [1, 2, 3]

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result

    # Mock del context manager AsyncSessionLocal()
    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__.return_value = mock_session

    with patch("src.infra.maintenance.AsyncSessionLocal", mock_session_local):
        deleted_count = await clean_unavailable_convocatorias(dias_gracia=30)

    assert deleted_count == 3
    # Debe haber 3 ejecuciones de execute: 1 para select, 1 para historial, 1 para convocatoria
    assert mock_session.execute.call_count == 3
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_clean_unavailable_convocatorias_no_records() -> None:
    # Simulamos que no hay registros
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result

    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__.return_value = mock_session

    with patch("src.infra.maintenance.AsyncSessionLocal", mock_session_local):
        deleted_count = await clean_unavailable_convocatorias(dias_gracia=30)

    assert deleted_count == 0
    # Solo el select
    assert mock_session.execute.call_count == 1
    # No hay commit ni delete
    assert mock_session.commit.call_count == 0
