"""
Tests de regresión para CompositeFundingScraper — fallback y escenarios de falla total.

Cubre: pipeline con todos los pasos fallidos (fetch y extract),
re-fetch en fallback de extract, empty_state_markers, y métricas.
"""

from unittest.mock import patch
from uuid import uuid4

import pytest

from src.core.domain.entities import Fuente, RulesConfig, Snapshot
from src.core.domain.exceptions import ExtractionError, NetworkError
from src.infra.scraping.funding_pipeline import CompositeFundingScraper
from src.infra.sources.catalog import ScrapeStep, SourceProfile


async def _noop_sleep(_: float) -> None:
    return None


def _make_profile_2steps() -> SourceProfile:
    return SourceProfile(
        key="TEST_PIPELINE",
        root_url="https://test.cl/",
        list_url="https://test.cl/fondos/",
        steps=(
            ScrapeStep(fetcher="json_api", extractor="json_api", url="https://test.cl/api/fondos"),
            ScrapeStep(fetcher="html_static", extractor="html_static", url="https://test.cl/fondos/"),
        ),
        min_request_interval_seconds=0,
    )


def _make_profile_3steps() -> SourceProfile:
    return SourceProfile(
        key="TEST_3STEP",
        root_url="https://test.cl/",
        list_url="https://test.cl/fondos/",
        steps=(
            ScrapeStep(fetcher="json_api", extractor="json_api", url="https://test.cl/api/"),
            ScrapeStep(fetcher="html_static", extractor="html_static", url="https://test.cl/page/"),
            ScrapeStep(fetcher="llm", extractor="llm", url="https://test.cl/llm/"),
        ),
        min_request_interval_seconds=0,
    )


@pytest.fixture
def fuente_test() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="TEST_PIPELINE",
        url_base="https://test.cl/",  # type: ignore
        configuracion_reglas=RulesConfig(nombre="TEST_PIPELINE", url_busqueda="https://test.cl/fondos/"),  # type: ignore
    )


@pytest.mark.asyncio
async def test_fetch_all_steps_fail_raises_network_error(fuente_test: Fuente) -> None:
    profile = _make_profile_2steps()
    scraper = CompositeFundingScraper(profile)
    scraper._sleep = _noop_sleep

    with (
        patch.object(scraper._json_api, "fetch", side_effect=NetworkError("API down")),
        patch.object(scraper._html_static, "fetch", side_effect=NetworkError("HTML down")),
    ):
        with pytest.raises(NetworkError):
            await scraper.fetch(fuente_test)

    assert scraper._metrics.final_status == "FETCH_FAILED"
    assert len(scraper._metrics.step_metrics) == 2
    assert all(m["status"] == "FAILED" for m in scraper._metrics.step_metrics)


@pytest.mark.asyncio
async def test_fetch_first_fails_second_succeeds(fuente_test: Fuente) -> None:
    profile = _make_profile_2steps()
    scraper = CompositeFundingScraper(profile)
    scraper._sleep = _noop_sleep

    fallback_snapshot = Snapshot(
        fuente_id=fuente_test.id,
        contenido_crudo="<html><body>OK</body></html>",
        hash_contenido="hash",
        estado_ejecucion="SUCCESS",
    )

    with (
        patch.object(scraper._json_api, "fetch", side_effect=NetworkError("API down")),
        patch.object(scraper._html_static, "fetch", return_value=fallback_snapshot),
    ):
        snapshot = await scraper.fetch(fuente_test)

    assert snapshot.contenido_crudo == "<html><body>OK</body></html>"
    assert scraper._metrics.step_metrics[0]["status"] == "FAILED"
    assert scraper._metrics.step_metrics[1]["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_extract_all_steps_fail_raises_extraction_error(fuente_test: Fuente) -> None:
    profile = _make_profile_2steps()
    scraper = CompositeFundingScraper(profile)
    scraper._sleep = _noop_sleep

    snapshot = Snapshot(
        fuente_id=fuente_test.id,
        contenido_crudo="<html>empty</html>",
        hash_contenido="hash",
        estado_ejecucion="SUCCESS",
    )
    scraper._state = None

    with (
        patch.object(scraper._json_api, "fetch", side_effect=NetworkError("API down")),
        patch.object(scraper._json_api, "extract", side_effect=ExtractionError("JSON bad")),
        patch.object(scraper._html_static, "fetch", side_effect=NetworkError("HTML down")),
        patch.object(scraper._html_static, "extract", side_effect=ExtractionError("HTML bad")),
    ):
        with pytest.raises(ExtractionError, match="No se pudieron extraer datos"):
            await scraper.extract(snapshot, fuente_test)

    assert scraper._metrics.final_status == "EXTRACTION_FAILED"


@pytest.mark.asyncio
async def test_extract_fallback_re_fetch_and_extract_success(fuente_test: Fuente) -> None:
    profile = _make_profile_2steps()
    scraper = CompositeFundingScraper(profile)
    scraper._sleep = _noop_sleep

    initial_snapshot = Snapshot(
        fuente_id=fuente_test.id,
        contenido_crudo='{"data": []}',
        hash_contenido="h1",
        estado_ejecucion="SUCCESS",
    )
    scraper._state = None

    fallback_snapshot = Snapshot(
        fuente_id=fuente_test.id,
        contenido_crudo="<html><div class='item'>OK</div></html>",
        hash_contenido="h2",
        estado_ejecucion="SUCCESS",
    )

    with (
        patch.object(scraper._json_api, "fetch", side_effect=NetworkError("API down")),
        patch.object(scraper._json_api, "extract", return_value=[]),
        patch.object(scraper._html_static, "fetch", return_value=fallback_snapshot),
        patch.object(scraper._html_static, "extract", return_value=[{"identificador": "1", "titulo": "OK"}]),
    ):
        items = await scraper.extract(initial_snapshot, fuente_test)

    assert len(items) == 1
    assert scraper._metrics.final_status == "SUCCESS"


@pytest.mark.asyncio
async def test_extract_empty_state_marker_returns_empty(fuente_test: Fuente) -> None:
    profile = SourceProfile(
        key="TEST_EMPTY",
        root_url="https://test.cl/",
        list_url="https://test.cl/fondos/",
        steps=(
            ScrapeStep(fetcher="html_static", extractor="html_static", url="https://test.cl/fondos/"),
        ),
        empty_state_markers=("No hay convocatorias",),
        min_request_interval_seconds=0,
    )
    scraper = CompositeFundingScraper(profile)
    scraper._sleep = _noop_sleep

    empty_snapshot = Snapshot(
        fuente_id=fuente_test.id,
        contenido_crudo="<html><body>No hay convocatorias disponibles</body></html>",
        hash_contenido="hash",
        estado_ejecucion="SUCCESS",
    )
    scraper._state = None

    with (
        patch.object(scraper._html_static, "fetch", return_value=empty_snapshot),
        patch.object(scraper._html_static, "extract", return_value=[]),
    ):
        items = await scraper.extract(empty_snapshot, fuente_test)

    assert items == []
    assert scraper._metrics.final_status == "SUCCESS_EMPTY"


@pytest.mark.asyncio
async def test_fetch_metrics_recorded_per_step(fuente_test: Fuente) -> None:
    profile = _make_profile_3steps()
    scraper = CompositeFundingScraper(profile)
    scraper._sleep = _noop_sleep

    success_snapshot = Snapshot(
        fuente_id=fuente_test.id,
        contenido_crudo="<html>OK</html>",
        hash_contenido="hash",
        estado_ejecucion="SUCCESS",
    )

    with (
        patch.object(scraper._json_api, "fetch", side_effect=NetworkError("fail 1")),
        patch.object(scraper._html_static, "fetch", side_effect=NetworkError("fail 2")),
        patch.object(scraper._llm, "fetch", return_value=success_snapshot),
    ):
        await scraper.fetch(fuente_test)

    assert len(scraper._metrics.step_metrics) == 3
    assert scraper._metrics.step_metrics[0]["status"] == "FAILED"
    assert scraper._metrics.step_metrics[1]["status"] == "FAILED"
    assert scraper._metrics.step_metrics[2]["status"] == "SUCCESS"
    assert scraper._metrics.step_metrics[2]["fetcher"] == "llm"
