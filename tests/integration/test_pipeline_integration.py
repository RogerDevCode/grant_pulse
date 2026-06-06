"""
Tests de integración para el pipeline de scraping compuesto.
Valida que todos los perfiles del catálogo se construyan correctamente
y que la cascada de fallback funcione como se espera.
"""

from uuid import uuid4

import pytest

from src.core.domain.entities import Fuente, RulesConfig, Snapshot
from src.infra.scraping.funding_pipeline import CompositeFundingScraper, build_scraper_for_source
from src.infra.sources.catalog import iter_source_profiles, resolve_source_profile


async def _noop_sleep(_: float) -> None:
    return None


class TestCatalogProfiles:
    """Todos los perfiles del catálogo deben resolver y construir scrapers válidos."""

    @pytest.fixture(params=[p.key for p in iter_source_profiles()])
    def profile_key(self, request: pytest.FixtureRequest) -> str:
        return str(request.param)

    def test_profile_resolves(self, profile_key: str) -> None:
        profile = resolve_source_profile(profile_key)
        assert profile is not None
        assert profile.key == profile_key
        assert len(profile.steps) >= 1

    def test_profile_builds_composite_scraper(self, profile_key: str) -> None:
        profile = resolve_source_profile(profile_key)
        assert profile is not None
        scraper = CompositeFundingScraper(profile)
        assert scraper is not None
        assert scraper._profile is profile  # pyright: ignore[reportPrivateUsage]

    def test_profile_first_step_has_fetcher_and_extractor(self, profile_key: str) -> None:
        profile = resolve_source_profile(profile_key)
        assert profile is not None
        step = profile.steps[0]
        assert step.fetcher in {"html_static", "json_api", "rss_feed", "wp_ajax", "curl_cffi", "browser", "llm", "subdere_homepage", "fosis_multipage"}
        assert step.extractor in {"html_static", "json_api", "rss_feed", "wp_ajax", "curl_cffi", "llm", "subdere_homepage", "fosis_multipage"}


class TestPipelineFallback:
    """Valida que el pipeline cascadae correctamente entre pasos."""

    @pytest.mark.asyncio
    async def test_corfo_falls_back_from_wp_ajax_to_curl_cffi(self) -> None:
        profile = resolve_source_profile("CORFO")
        assert profile is not None
        assert len(profile.steps) >= 2
        assert profile.steps[0].fetcher == "wp_ajax"
        assert profile.steps[1].fetcher == "curl_cffi"

    @pytest.mark.asyncio
    async def test_anid_primary_is_rss(self) -> None:
        profile = resolve_source_profile("ANID")
        assert profile is not None
        assert profile.steps[0].fetcher == "rss_feed"

    @pytest.mark.asyncio
    async def test_fia_primary_is_json_api_with_pagination(self) -> None:
        profile = resolve_source_profile("FIA")
        assert profile is not None
        assert profile.steps[0].fetcher == "json_api"

    @pytest.mark.asyncio
    async def test_prochile_primary_is_curl_cffi(self) -> None:
        profile = resolve_source_profile("PROCHILE")
        assert profile is not None
        assert profile.steps[0].fetcher == "curl_cffi"

    @pytest.mark.asyncio
    async def test_indap_primary_is_html_static(self) -> None:
        profile = resolve_source_profile("INDAP")
        assert profile is not None
        assert profile.steps[0].fetcher == "html_static"

    @pytest.mark.asyncio
    async def test_sercotec_primary_is_json_api(self) -> None:
        profile = resolve_source_profile("SERCOTEC")
        assert profile is not None
        assert profile.steps[0].fetcher == "json_api"

    @pytest.mark.asyncio
    async def test_fosis_uses_multipage_strategy(self) -> None:
        profile = resolve_source_profile("FOSIS")
        assert profile is not None
        assert profile.steps[0].fetcher == "fosis_multipage"

    @pytest.mark.asyncio
    async def test_subdere_uses_homepage_strategy(self) -> None:
        profile = resolve_source_profile("SUBDERE")
        assert profile is not None
        fetchers = [s.fetcher for s in profile.steps]
        assert "subdere_homepage" in fetchers


class TestBuildScraperFactory:
    """Valida la factory build_scraper_for_source para perfiles conocidos y desconocidos."""

    @pytest.mark.parametrize("nombre", ["CORFO", "SERCOTEC", "FIA", "ANID", "INDAP", "FOSIS", "SUBDERE", "PROCHILE"])
    def test_known_source_returns_composite(self, nombre: str) -> None:
        fuente = Fuente(
            id=uuid4(),
            nombre=nombre,
            url_base="https://example.com/",  # type: ignore[arg-type]
            configuracion_reglas=RulesConfig(nombre=nombre, url_busqueda="https://example.com/page/"),  # type: ignore[arg-type]
        )
        scraper = build_scraper_for_source(fuente)
        assert isinstance(scraper, CompositeFundingScraper)

    def test_unknown_source_returns_html_static(self) -> None:
        fuente = Fuente(
            id=uuid4(),
            nombre="UNKNOWN_XYZ",
            url_base="https://example.com/",  # type: ignore[arg-type]
            configuracion_reglas=RulesConfig(
                nombre="UNKNOWN_XYZ",
                url_busqueda="https://example.com/page/",  # type: ignore[arg-type]
                estrategia="html_static",
            ),
        )
        scraper = build_scraper_for_source(fuente)
        from src.infra.scraping.html_static import HtmlStaticScraper

        assert isinstance(scraper, HtmlStaticScraper)

    def test_unknown_rss_feed_strategy(self) -> None:
        fuente = Fuente(
            id=uuid4(),
            nombre="UNKNOWN_RSS",
            url_base="https://example.com/",  # type: ignore[arg-type]
            configuracion_reglas=RulesConfig(
                nombre="UNKNOWN_RSS",
                url_busqueda="https://example.com/feed/",  # type: ignore[arg-type]
                estrategia="rss_feed",
            ),
        )
        scraper = build_scraper_for_source(fuente)
        from src.infra.scraping.rss_feed import RssFeedScraper

        assert isinstance(scraper, RssFeedScraper)

    def test_unknown_wp_ajax_strategy(self) -> None:
        fuente = Fuente(
            id=uuid4(),
            nombre="UNKNOWN_WP",
            url_base="https://example.com/",  # type: ignore[arg-type]
            configuracion_reglas=RulesConfig(
                nombre="UNKNOWN_WP",
                url_busqueda="https://example.com/page/",  # type: ignore[arg-type]
                estrategia="wp_ajax",
            ),
        )
        scraper = build_scraper_for_source(fuente)
        from src.infra.scraping.wp_ajax import WpAjaxScraper

        assert isinstance(scraper, WpAjaxScraper)


class TestPipelineFallbackExecution:
    """Prueba la ejecución real de la cascada de fallback con mocks."""

    @pytest.mark.asyncio
    async def test_first_step_failure_triggers_fallback(self) -> None:
        from unittest.mock import patch

        profile = resolve_source_profile("CORFO")
        assert profile is not None
        scraper = CompositeFundingScraper(profile)
        scraper._sleep = _noop_sleep

        fuente = Fuente(
            id=uuid4(),
            nombre="CORFO",
            url_base="https://www.corfo.gob.cl/",  # type: ignore[arg-type]
            configuracion_reglas=RulesConfig(
                nombre="CORFO",
                url_busqueda="https://www.corfo.gob.cl/sites/cpp/programasyconvocatorias/",  # type: ignore[arg-type]
            ),
        )

        fallback_snapshot = Snapshot(
            fuente_id=fuente.id,
            contenido_crudo="<html><body><div class='item'>OK</div></body></html>",
            hash_contenido="hash",
            estado_ejecucion="SUCCESS",
        )

        with (
            patch.object(scraper._wp_ajax, "fetch", side_effect=Exception("AJAX failed")),
            patch.object(scraper._curl_cffi, "fetch", return_value=fallback_snapshot),
            patch.object(scraper._html_static, "extract", return_value=[{"identificador": "1", "titulo": "OK"}]),
        ):
            snapshot = await scraper.fetch(fuente)
            assert snapshot.contenido_crudo == fallback_snapshot.contenido_crudo

            items = await scraper.extract(snapshot, fuente)
            assert len(items) == 1
            assert scraper._state is not None
            assert scraper._state.step_index == 1

    @pytest.mark.asyncio
    async def test_all_steps_fail_raises_last_error(self) -> None:
        from unittest.mock import patch

        from src.core.domain.exceptions import NetworkError

        profile = resolve_source_profile("FOSIS")
        assert profile is not None
        scraper = CompositeFundingScraper(profile)
        scraper._sleep = _noop_sleep

        fuente = Fuente(
            id=uuid4(),
            nombre="FOSIS",
            url_base="https://www.fosis.gob.cl/",  # type: ignore[arg-type]
            configuracion_reglas=RulesConfig(
                nombre="FOSIS",
                url_busqueda="https://www.fosis.gob.cl/es/programas/autonomia-economica/",  # type: ignore[arg-type]
            ),
        )

        last_error = NetworkError("All failed")

        with patch.object(scraper._fosis_multipage, "fetch", side_effect=last_error):
            with pytest.raises(NetworkError, match="All failed"):
                await scraper.fetch(fuente)
