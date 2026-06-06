"""Tests para CurlCffiScraper."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.core.domain.entities import Fuente, RulesConfig, Snapshot
from src.core.domain.exceptions import NetworkError
from src.infra.scraping.curl_cffi import CurlCffiScraper


@pytest.fixture
def fuente_fosis() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="FOSIS",
        url_base="https://www.fosis.gob.cl/",  # type: ignore[arg-type]
        configuracion_reglas=RulesConfig(
            nombre="FOSIS",
            url_busqueda="https://www.fosis.gob.cl/es/programas/",  # type: ignore[arg-type]
            estrategia="curl_cffi",
        ),
    )


def test_curl_cffi_scraper_init_defaults() -> None:
    scraper = CurlCffiScraper()
    assert scraper._timeout == 30
    assert scraper._impersonate == "chrome120"


def test_curl_cffi_scraper_custom_impersonate() -> None:
    scraper = CurlCffiScraper(timeout=15, impersonate="chrome131")
    assert scraper._timeout == 15
    assert scraper._impersonate == "chrome131"


@pytest.mark.asyncio
async def test_fetch_raises_on_empty_response(fuente_fosis: Fuente) -> None:
    scraper = CurlCffiScraper()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = ""

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response

    with patch.object(scraper, "_session", mock_session):
        with pytest.raises(NetworkError, match="respuesta vacía"):
            await scraper.fetch(fuente_fosis)


@pytest.mark.asyncio
async def test_fetch_raises_on_http_error(fuente_fosis: Fuente) -> None:
    scraper = CurlCffiScraper()
    mock_response = MagicMock()
    mock_response.status_code = 403

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response

    with patch.object(scraper, "_session", mock_session):
        with pytest.raises(NetworkError, match="HTTP 403"):
            await scraper.fetch(fuente_fosis)


@pytest.mark.asyncio
async def test_fetch_success(fuente_fosis: Fuente) -> None:
    scraper = CurlCffiScraper()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body><h1>Programas FOSIS</h1></body></html>"

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response

    with patch.object(scraper, "_session", mock_session):
        snapshot = await scraper.fetch(fuente_fosis)
        assert snapshot.estado_ejecucion == "SUCCESS"
        assert "Programas FOSIS" in snapshot.contenido_crudo
        assert mock_session.get.call_count == 1


@pytest.mark.asyncio
async def test_extract_delegates_to_html_static(fuente_fosis: Fuente) -> None:
    scraper = CurlCffiScraper()
    snapshot = Snapshot(
        fuente_id=fuente_fosis.id,
        contenido_crudo="<html><body><p>test</p></body></html>",
        hash_contenido="testhash",
        estado_ejecucion="SUCCESS",
    )

    with patch("src.infra.scraping.html_static.HtmlStaticScraper.extract", return_value=[]) as mock_extract:
        await scraper.extract(snapshot, fuente_fosis)
        assert mock_extract.call_count == 1
