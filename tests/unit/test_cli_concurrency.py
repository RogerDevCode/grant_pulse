import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.domain.entities import Fuente, RulesConfig
from src.infra.cli import run_all_active_sources


@pytest.fixture
def mock_fuentes():
    fuentes = []
    for i in range(5):
        fuente = Fuente(
            id=i + 1,
            nombre=f"Fuente {i}",
            url_base="https://ejemplo.com",
            activa=True,
            configuracion_reglas=RulesConfig(
                nombre=f"Fuente {i}",
                url_busqueda="https://ejemplo.com",
                estrategia="html_static",
            )
        )
        fuentes.append(fuente)
    return fuentes


@pytest.mark.asyncio
async def test_run_all_active_sources_concurrency(mock_fuentes):
    """
    Verifica que `run_all_active_sources` procesa las fuentes con concurrencia controlada
    y captura excepciones sin interrumpir el resto.
    """

    # Rastrear la concurrencia máxima
    active_tasks = 0
    max_active_tasks = 0
    lock = asyncio.Lock()

    async def mock_ejecutar_monitoreo(*_args, **_kwargs):
        nonlocal active_tasks, max_active_tasks

        async with lock:
            active_tasks += 1
            if active_tasks > max_active_tasks:
                max_active_tasks = active_tasks

        # Simular carga
        await asyncio.sleep(0.05)

        async with lock:
            active_tasks -= 1

        return [], []

    # Mock de repositorios y usecase
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session_cls = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    mock_fuente_repo = MagicMock()
    mock_fuente_repo.get_all_active = AsyncMock(return_value=mock_fuentes)

    mock_use_case = MagicMock()
    mock_use_case.ejecutar_monitoreo = AsyncMock(side_effect=mock_ejecutar_monitoreo)

    with patch("src.infra.cli.AsyncSessionLocal", mock_session_cls), \
         patch("src.infra.cli.SQLFuenteRepository", return_value=mock_fuente_repo), \
         patch("src.infra.cli.SQLSnapshotRepository"), \
         patch("src.infra.cli.SQLConvocatoriaRepository"), \
         patch("src.infra.cli.SQLNotificacionRepository"), \
         patch("src.infra.cli._apply_source_profile", lambda x: x), \
         patch("src.infra.cli._get_scraper"), \
         patch("src.infra.cli._get_notifier", new_callable=AsyncMock), \
         patch("src.infra.cli.MonitoreoUseCase", return_value=mock_use_case), \
         patch("src.infra.quality_report.generar_reporte_calidad", new_callable=AsyncMock):

        await run_all_active_sources()

    # Verificar que el use_case fue llamado para cada fuente
    assert mock_use_case.ejecutar_monitoreo.call_count == 5

    # La concurrencia máxima debería ser 3 por el semáforo
    assert max_active_tasks == 3


@pytest.mark.asyncio
async def test_run_all_active_sources_handles_exceptions(mock_fuentes):
    """
    Verifica que si una fuente falla, las demás se siguen procesando.
    """

    async def mock_ejecutar_monitoreo(fuente, *_args, **_kwargs):
        if fuente.nombre == "Fuente 2":
            raise Exception("Simulated error")
        return [], []

    # Mock de repositorios y usecase
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session_cls = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    mock_fuente_repo = MagicMock()
    mock_fuente_repo.get_all_active = AsyncMock(return_value=mock_fuentes)

    mock_use_case = MagicMock()
    mock_use_case.ejecutar_monitoreo = AsyncMock(side_effect=mock_ejecutar_monitoreo)

    with patch("src.infra.cli.AsyncSessionLocal", mock_session_cls), \
         patch("src.infra.cli.SQLFuenteRepository", return_value=mock_fuente_repo), \
         patch("src.infra.cli.SQLSnapshotRepository"), \
         patch("src.infra.cli.SQLConvocatoriaRepository"), \
         patch("src.infra.cli.SQLNotificacionRepository"), \
         patch("src.infra.cli._apply_source_profile", lambda x: x), \
         patch("src.infra.cli._get_scraper"), \
         patch("src.infra.cli._get_notifier", new_callable=AsyncMock), \
         patch("src.infra.cli.MonitoreoUseCase", return_value=mock_use_case), \
         patch("src.infra.quality_report.generar_reporte_calidad", new_callable=AsyncMock):

        await run_all_active_sources()

    # Verificar que se intentaron procesar todas
    assert mock_use_case.ejecutar_monitoreo.call_count == 5
