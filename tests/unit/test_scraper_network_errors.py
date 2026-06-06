"""
Tests de regresión para errores de red en scrapers (fetch phase).

Verifica que cada scraper traduzca httpx.RequestError/HTTPStatusError
a NetworkError con mensaje contextual y preservando la cadena de causas.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
import respx
from httpx import Response

from src.core.domain.entities import Fuente, RulesConfig, SelectorConfig
from src.core.domain.exceptions import NetworkError
from src.infra.scraping.html_static import HtmlStaticScraper
from src.infra.scraping.json_api import JsonApiScraper
from src.infra.scraping.llm_scraper import LlmScraper
from src.infra.scraping.rss_feed import RssFeedScraper


@pytest.fixture
def fuente_html() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="TEST_HTML",
        url_base="https://ejemplo.com",  # type: ignore
        configuracion_reglas=RulesConfig(
            nombre="TEST_HTML",
            url_busqueda="https://ejemplo.com/fondos",  # type: ignore
            selectores=SelectorConfig(contenedor_items="div", identificador="id", titulo="t", descripcion="d", link_detalle="l", estado="e"),
        ),
    )


@pytest.fixture
def fuente_json() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="TEST_JSON",
        url_base="https://ejemplo.com",  # type: ignore
        configuracion_reglas=RulesConfig(
            nombre="TEST_JSON",
            url_busqueda="https://ejemplo.com/api/fondos",  # type: ignore
            estrategia="json_api",
        ),
    )


@pytest.fixture
def fuente_rss() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="TEST_RSS",
        url_base="https://ejemplo.com",  # type: ignore
        configuracion_reglas=RulesConfig(
            nombre="TEST_RSS",
            url_busqueda="https://ejemplo.com/feed/",  # type: ignore
            estrategia="rss_feed",
        ),
    )


@pytest.fixture
def fuente_llm() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="TEST_LLM",
        url_base="https://ejemplo.com",  # type: ignore
        configuracion_reglas=RulesConfig(
            nombre="TEST_LLM",
            url_busqueda="https://ejemplo.com/fondos",  # type: ignore
            estrategia="llm",
            selectores=SelectorConfig(contenedor_items="div", identificador="id", titulo="t", descripcion="d", link_detalle="l", estado="e"),
        ),
    )


# --- HtmlStaticScraper ---


@pytest.mark.asyncio
@respx.mock
async def test_html_static_fetch_connection_error(fuente_html: Fuente) -> None:
    url = str(fuente_html.configuracion_reglas.url_busqueda)
    respx.get(url).mock(side_effect=httpx.ConnectError("Connection refused"))

    scraper = HtmlStaticScraper()
    with pytest.raises(NetworkError, match="Error de red"):
        await scraper.fetch(fuente_html)


@pytest.mark.asyncio
@respx.mock
async def test_html_static_fetch_timeout_error(fuente_html: Fuente) -> None:
    url = str(fuente_html.configuracion_reglas.url_busqueda)
    respx.get(url).mock(side_effect=httpx.TimeoutException("Read timeout"))

    scraper = HtmlStaticScraper()
    with pytest.raises(NetworkError, match="Error de red"):
        await scraper.fetch(fuente_html)


@pytest.mark.asyncio
@respx.mock
async def test_html_static_fetch_http_403(fuente_html: Fuente) -> None:
    url = str(fuente_html.configuracion_reglas.url_busqueda)
    respx.get(url).mock(return_value=Response(403, text="Forbidden"))

    scraper = HtmlStaticScraper()
    with pytest.raises(NetworkError, match="Error HTTP 403"):
        await scraper.fetch(fuente_html)


# --- JsonApiScraper ---


@pytest.mark.asyncio
@respx.mock
async def test_json_api_fetch_connection_error(fuente_json: Fuente) -> None:
    url = str(fuente_json.configuracion_reglas.url_busqueda)
    respx.get(url).mock(side_effect=httpx.ConnectError("Connection refused"))

    scraper = JsonApiScraper()
    with pytest.raises(NetworkError, match="Error de red"):
        await scraper.fetch(fuente_json)


@pytest.mark.asyncio
@respx.mock
async def test_json_api_fetch_timeout_error(fuente_json: Fuente) -> None:
    url = str(fuente_json.configuracion_reglas.url_busqueda)
    respx.get(url).mock(side_effect=httpx.TimeoutException("Read timeout"))

    scraper = JsonApiScraper()
    with pytest.raises(NetworkError, match="Error de red"):
        await scraper.fetch(fuente_json)


@pytest.mark.asyncio
@respx.mock
async def test_json_api_fetch_http_500(fuente_json: Fuente) -> None:
    url = str(fuente_json.configuracion_reglas.url_busqueda)
    respx.get(url).mock(return_value=Response(500, text="Internal Server Error"))

    scraper = JsonApiScraper()
    with pytest.raises(NetworkError, match="Error HTTP 500"):
        await scraper.fetch(fuente_json)


# --- RssFeedScraper ---


@pytest.mark.asyncio
@respx.mock
async def test_rss_feed_fetch_connection_error(fuente_rss: Fuente) -> None:
    url = str(fuente_rss.configuracion_reglas.url_busqueda)
    respx.get(url).mock(side_effect=httpx.ConnectError("DNS failure"))

    scraper = RssFeedScraper()
    with pytest.raises(NetworkError, match="Error de red"):
        await scraper.fetch(fuente_rss)


@pytest.mark.asyncio
@respx.mock
async def test_rss_feed_fetch_timeout_error(fuente_rss: Fuente) -> None:
    url = str(fuente_rss.configuracion_reglas.url_busqueda)
    respx.get(url).mock(side_effect=httpx.TimeoutException("Pool timeout"))

    scraper = RssFeedScraper()
    with pytest.raises(NetworkError, match="Error de red"):
        await scraper.fetch(fuente_rss)


@pytest.mark.asyncio
@respx.mock
async def test_rss_feed_fetch_http_404(fuente_rss: Fuente) -> None:
    url = str(fuente_rss.configuracion_reglas.url_busqueda)
    respx.get(url).mock(return_value=Response(404, text="Not Found"))

    scraper = RssFeedScraper()
    with pytest.raises(NetworkError, match="Error HTTP 404"):
        await scraper.fetch(fuente_rss)


# --- LlmScraper ---


@pytest.mark.asyncio
async def test_llm_scraper_fetch_connection_error(fuente_llm: Fuente) -> None:
    scraper = LlmScraper()

    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection refused")):
        with pytest.raises(NetworkError, match="Error de red"):
            await scraper.fetch(fuente_llm)


@pytest.mark.asyncio
async def test_llm_scraper_fetch_timeout_error(fuente_llm: Fuente) -> None:
    scraper = LlmScraper()

    with patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("Read timeout")):
        with pytest.raises(NetworkError, match="Error de red"):
            await scraper.fetch(fuente_llm)


@pytest.mark.asyncio
async def test_llm_scraper_fetch_http_502(fuente_llm: Fuente) -> None:
    scraper = LlmScraper()

    mock_response = AsyncMock(spec=Response)
    mock_response.status_code = 502
    mock_response.text = "Bad Gateway"

    def _raise_502() -> None:
        raise httpx.HTTPStatusError(
            "Server error '502 Bad Gateway'",
            request=httpx.Request("GET", "https://ejemplo.com/fondos"),
            response=httpx.Response(502, text="Bad Gateway"),
        )

    mock_response.raise_for_status = _raise_502

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        with pytest.raises(NetworkError, match="Error HTTP 502"):
            await scraper.fetch(fuente_llm)
