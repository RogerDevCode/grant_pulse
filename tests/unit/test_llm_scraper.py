"""
Tests unitarios para el scraper basado en LLM (OpenRouter).
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import Response

from src.core.domain.entities import Fuente, RulesConfig, SelectorConfig, Snapshot
from src.infra.scraping.llm_scraper import LlmScraper


@pytest.fixture
def mock_fuente_llm() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="Test LLM",
        url_base="https://ejemplo.com",  # type: ignore
        configuracion_reglas=RulesConfig(
            nombre="Test",
            url_busqueda="https://ejemplo.com/fondos",  # type: ignore
            estrategia="llm",
            selectores=SelectorConfig(  # Aunque no se usen, son obligatorios en el modelo actual
                contenedor_items="div", identificador="id", titulo="t", descripcion="d", link_detalle="l", estado="e"
            ),
        ),
    )


@pytest.mark.asyncio
async def test_llm_scraper_extract_success(mock_fuente_llm: Fuente) -> None:
    scraper = LlmScraper()
    snapshot = Snapshot(
        fuente_id=mock_fuente_llm.id,
        contenido_crudo="<html><body>Fondo Semilla de 10M abierto hasta diciembre</body></html>",
        hash_contenido="123",
        estado_ejecucion="SUCCESS",
    )

    # Mock del cliente LLM
    mock_items = [
        {
            "identificador": "fondo-semilla",
            "titulo": "Fondo Semilla",
            "descripcion": "Apoyo inicial",
            "url_detalle": "/detalle",
            "estado": "ABIERTO",
            "fecha_cierre": "2026-12-31",
            "monto": "10000000",
        }
    ]

    with patch.object(scraper.llm_client, "extract_from_html", return_value=mock_items):
        resultados = await scraper.extract(snapshot, mock_fuente_llm)

        assert len(resultados) == 1
        assert resultados[0]["titulo"] == "Fondo Semilla"
        assert resultados[0]["monto"] == "10000000"


@pytest.mark.asyncio
async def test_llm_scraper_fetch_success(mock_fuente_llm: Fuente) -> None:
    scraper = LlmScraper()

    with patch(
        "httpx.AsyncClient.get",
        return_value=AsyncMock(spec=Response, status_code=200, text="<html></html>", raise_for_status=lambda: None),
    ):
        snapshot = await scraper.fetch(mock_fuente_llm)
        assert snapshot.contenido_crudo == "<html></html>"
        assert snapshot.estado_ejecucion == "SUCCESS"
