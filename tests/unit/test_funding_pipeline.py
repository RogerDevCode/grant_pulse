"""Tests para el pipeline institucional compuesto."""

from unittest.mock import patch
from uuid import uuid4

import pytest

from src.core.domain.entities import Fuente, JsonMappingConfig, RulesConfig, Snapshot
from src.infra.scraping.funding_pipeline import CompositeFundingScraper, build_scraper_for_source
from src.infra.sources.catalog import resolve_source_profile


async def _noop_sleep(_: float) -> None:
    return None


@pytest.fixture
def fuente_corfo() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="CORFO",
        url_base="https://www.corfo.gob.cl/",  # type: ignore[arg-type]
        configuracion_reglas=RulesConfig(
            nombre="CORFO",
            url_busqueda="https://www.corfo.gob.cl/sites/cpp/programasyconvocatorias/",  # type: ignore[arg-type]
            estrategia="wp_ajax",
        ),
    )


@pytest.fixture
def fuente_sercotec() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="SERCOTEC",
        url_base="https://www.sercotec.cl/",  # type: ignore[arg-type]
        configuracion_reglas=RulesConfig(
            nombre="SERCOTEC",
            url_busqueda="https://www.sercotec.cl/wp-json/wp/v2/programas",  # type: ignore[arg-type]
            estrategia="json_api",
            json_mapping=JsonMappingConfig(
                root_path="",
                identificador="slug",
                titulo="title.rendered",
                link_detalle="link",
            ),
        ),
    )


def test_build_scraper_for_known_profile_returns_composite(fuente_corfo: Fuente) -> None:
    scraper = build_scraper_for_source(fuente_corfo)
    assert isinstance(scraper, CompositeFundingScraper)


def test_build_scraper_for_sercotec_returns_composite(fuente_sercotec: Fuente) -> None:
    scraper = build_scraper_for_source(fuente_sercotec)
    assert isinstance(scraper, CompositeFundingScraper)


@pytest.mark.asyncio
async def test_corfo_pipeline_falls_back_from_wp_ajax_to_curl_cffi(fuente_corfo: Fuente) -> None:
    profile = resolve_source_profile("CORFO")
    assert profile is not None
    scraper = CompositeFundingScraper(profile)
    scraper._sleep = _noop_sleep

    fallback_snapshot = Snapshot(
        fuente_id=fuente_corfo.id,
        contenido_crudo="<html><body><div class='item'>OK</div></body></html>",
        hash_contenido="hash",
        estado_ejecucion="SUCCESS",
    )

    with (
        patch.object(scraper._wp_ajax, "fetch", side_effect=Exception("AJAX failed")) as mock_ajax_fetch,
        patch.object(scraper._curl_cffi, "fetch", return_value=fallback_snapshot) as mock_curl_fetch,
        patch.object(
            scraper._html_static, "extract", return_value=[{"identificador": "1", "titulo": "OK"}]
        ) as mock_html_extract,
    ):
        snapshot = await scraper.fetch(fuente_corfo)
        assert snapshot.contenido_crudo == fallback_snapshot.contenido_crudo
        assert mock_ajax_fetch.call_count == 1
        assert mock_curl_fetch.call_count == 1

        items = await scraper.extract(snapshot, fuente_corfo)
        assert items == [{"identificador": "1", "titulo": "OK"}]
        assert mock_html_extract.call_count == 1
        assert scraper._state is not None
        assert scraper._state.step_index == 1


@pytest.mark.asyncio
async def test_sercotec_pipeline_uses_json_api_as_primary(fuente_sercotec: Fuente) -> None:
    profile = resolve_source_profile("SERCOTEC")
    assert profile is not None
    assert profile.steps[0].fetcher == "json_api"

    scraper = CompositeFundingScraper(profile)
    scraper._sleep = _noop_sleep

    json_snapshot = Snapshot(
        fuente_id=fuente_sercotec.id,
        contenido_crudo='[{"slug":"test","title":{"rendered":"Test Program"},"link":"https://sercotec.cl/test/"}]',
        hash_contenido="hash",
        estado_ejecucion="SUCCESS",
    )

    with (
        patch.object(scraper._json_api, "fetch", return_value=json_snapshot) as mock_json_fetch,
    ):
        await scraper.fetch(fuente_sercotec)
        assert mock_json_fetch.call_count == 1


@pytest.mark.asyncio
async def test_anid_pipeline_uses_rss_feed_as_primary() -> None:
    profile = resolve_source_profile("ANID")
    assert profile is not None
    assert profile.steps[0].fetcher == "rss_feed"
    assert profile.steps[0].extractor == "rss_feed"


@pytest.mark.asyncio
async def test_fia_pipeline_uses_json_api_as_primary() -> None:
    profile = resolve_source_profile("FIA")
    assert profile is not None
    assert profile.steps[0].fetcher == "json_api"
    assert profile.steps[0].extractor == "json_api"


def test_build_scraper_for_unknown_returns_html_static() -> None:
    fuente = Fuente(
        id=uuid4(),
        nombre="UNKNOWN_SOURCE",
        url_base="https://example.com/",  # type: ignore[arg-type]
        configuracion_reglas=RulesConfig(
            nombre="UNKNOWN_SOURCE",
            url_busqueda="https://example.com/page/",  # type: ignore[arg-type]
            estrategia="html_static",
        ),
    )
    scraper = build_scraper_for_source(fuente)
    from src.infra.scraping.html_static import HtmlStaticScraper

    assert isinstance(scraper, HtmlStaticScraper)


def test_build_scraper_for_unknown_rss_feed_strategy() -> None:
    fuente = Fuente(
        id=uuid4(),
        nombre="UNKNOWN_SOURCE",
        url_base="https://example.com/",  # type: ignore[arg-type]
        configuracion_reglas=RulesConfig(
            nombre="UNKNOWN_SOURCE",
            url_busqueda="https://example.com/feed/",  # type: ignore[arg-type]
            estrategia="rss_feed",
        ),
    )
    scraper = build_scraper_for_source(fuente)
    from src.infra.scraping.rss_feed import RssFeedScraper

    assert isinstance(scraper, RssFeedScraper)


def test_build_scraper_for_unknown_wp_ajax_strategy() -> None:
    fuente = Fuente(
        id=uuid4(),
        nombre="UNKNOWN_SOURCE",
        url_base="https://example.com/",  # type: ignore[arg-type]
        configuracion_reglas=RulesConfig(
            nombre="UNKNOWN_SOURCE",
            url_busqueda="https://example.com/page/",  # type: ignore[arg-type]
            estrategia="wp_ajax",
        ),
    )
    scraper = build_scraper_for_source(fuente)
    from src.infra.scraping.wp_ajax import WpAjaxScraper

    assert isinstance(scraper, WpAjaxScraper)
