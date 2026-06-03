"""Tests para la ruta JSON API."""

import json
from uuid import uuid4

import httpx
import pytest
import respx

from src.core.domain.entities import Fuente, JsonMappingConfig, PaginationConfig, RulesConfig, Snapshot
from src.core.domain.exceptions import ExtractionError
from src.infra.scraping.json_api import JsonApiScraper, _set_query_param


@pytest.fixture
def fuente_json() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="CORFO_API",
        url_base="https://www.corfo.gob.cl/",  # type: ignore[arg-type]
        configuracion_reglas=RulesConfig(
            nombre="CORFO_API",
            url_busqueda="https://www.corfo.cl/api/jsonws/programasyconvocatorias.programasyconvocatorias/get-programas-y-convocatorias",  # type: ignore[arg-type]
            estrategia="json_api",
            json_mapping=JsonMappingConfig(
                root_path="data.items",
                identificador="programaId",
                titulo="nombre",
                descripcion="descripcion",
                link_detalle="url",
                estado="estado",
                fecha_cierre="fechaTermino",
                monto="montoMaximo",
            ),
        ),
    )


@pytest.fixture
def fuente_paginada() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="FIA_TEST",
        url_base="https://example.com/",  # type: ignore[arg-type]
        configuracion_reglas=RulesConfig(
            nombre="FIA_TEST",
            url_busqueda="https://example.com/api/convocatorias?per_page=2",  # type: ignore[arg-type]
            estrategia="json_api",
            json_mapping=JsonMappingConfig(
                root_path=None,
                identificador="id",
                titulo="title.rendered",
                link_detalle="link",
                estado="status",
                paginacion=PaginationConfig(
                    total_pages_header="X-WP-TotalPages",
                    total_items_header="X-WP-Total",
                    page_param="page",
                    per_page_param="per_page",
                    max_pages=50,
                ),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_json_api_root_path_invalid_raises_extraction_error(fuente_json: Fuente) -> None:
    scraper = JsonApiScraper()
    snapshot = Snapshot(
        fuente_id=fuente_json.id,
        contenido_crudo='{"data": {"items": {"not": "a list"}}}',
        hash_contenido="hash",
        estado_ejecucion="SUCCESS",
    )

    with pytest.raises(ExtractionError, match="no devolvió una lista"):
        await scraper.extract(snapshot, fuente_json)


def test_set_query_param_adds_new() -> None:
    result = _set_query_param("https://example.com/api?per_page=100", "page", "2")
    assert "page=2" in result
    assert "per_page=100" in result


def test_set_query_param_replaces_existing() -> None:
    result = _set_query_param("https://example.com/api?page=1&per_page=100", "page", "3")
    assert "page=3" in result
    assert "per_page=100" in result


def test_pagination_config_defaults() -> None:
    p = PaginationConfig()
    assert p.total_pages_header is None
    assert p.page_param == "page"
    assert p.per_page_param == "per_page"
    assert p.max_pages == 50


@pytest.mark.asyncio
@respx.mock
async def test_fetch_paginated_consolidates_all_pages(fuente_paginada: Fuente) -> None:
    scraper = JsonApiScraper()

    page1 = [{"id": 1, "title": {"rendered": "A"}, "link": "https://a.cl", "status": "publish"}]
    page2 = [{"id": 2, "title": {"rendered": "B"}, "link": "https://b.cl", "status": "publish"}]

    base = "https://example.com/api/convocatorias"

    respx.get(base, params={"per_page": "2", "page": "1"}).mock(
        return_value=httpx.Response(200, json=page1, headers={"X-WP-TotalPages": "2", "X-WP-Total": "2"})
    )
    respx.get(base, params={"per_page": "2", "page": "2"}).mock(
        return_value=httpx.Response(200, json=page2, headers={"X-WP-TotalPages": "2", "X-WP-Total": "2"})
    )

    snapshot = await scraper.fetch(fuente_paginada)

    data = json.loads(snapshot.contenido_crudo)
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["id"] == 1
    assert data[1]["id"] == 2


@pytest.mark.asyncio
@respx.mock
async def test_fetch_no_pagination_single_request(fuente_json: Fuente) -> None:
    scraper = JsonApiScraper()

    single_page = [{"programaId": "P1", "nombre": "Prog 1", "estado": "ABIERTO"}]
    url = "https://www.corfo.cl/api/jsonws/programasyconvocatorias.programasyconvocatorias/get-programas-y-convocatorias"

    respx.get(url).mock(
        return_value=httpx.Response(200, json={"data": {"items": single_page}})
    )

    snapshot = await scraper.fetch(fuente_json)

    data = json.loads(snapshot.contenido_crudo)
    assert "data" in data
    assert "items" in data["data"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_paginated_respects_max_pages() -> None:
    scraper = JsonApiScraper()

    fuente = Fuente(
        id=uuid4(),
        nombre="MAX_PAGES_TEST",
        url_base="https://example.com/",  # type: ignore[arg-type]
        configuracion_reglas=RulesConfig(
            nombre="MAX_PAGES_TEST",
            url_busqueda="https://example.com/api?per_page=1",  # type: ignore[arg-type]
            estrategia="json_api",
            json_mapping=JsonMappingConfig(
                root_path=None,
                identificador="id",
                titulo="name",
                paginacion=PaginationConfig(
                    total_pages_header="X-WP-TotalPages",
                    max_pages=2,
                ),
            ),
        ),
    )

    page1 = [{"id": 1, "name": "A"}]
    page2 = [{"id": 2, "name": "B"}]

    base = "https://example.com/api"
    respx.get(base, params={"per_page": "1", "page": "1"}).mock(
        return_value=httpx.Response(200, json=page1, headers={"X-WP-TotalPages": "10", "X-WP-Total": "100"})
    )
    respx.get(base, params={"per_page": "1", "page": "2"}).mock(
        return_value=httpx.Response(200, json=page2, headers={"X-WP-TotalPages": "10", "X-WP-Total": "100"})
    )

    snapshot = await scraper.fetch(fuente)

    data = json.loads(snapshot.contenido_crudo)
    assert len(data) == 2  # max_pages=2, so only 2 pages fetched


@pytest.mark.asyncio
@respx.mock
async def test_fetch_paginated_empty_page_stops_early() -> None:
    scraper = JsonApiScraper()

    fuente = Fuente(
        id=uuid4(),
        nombre="EMPTY_PAGE_TEST",
        url_base="https://example.com/",  # type: ignore[arg-type]
        configuracion_reglas=RulesConfig(
            nombre="EMPTY_PAGE_TEST",
            url_busqueda="https://example.com/api?per_page=1",  # type: ignore[arg-type]
            estrategia="json_api",
            json_mapping=JsonMappingConfig(
                root_path=None,
                identificador="id",
                titulo="name",
                paginacion=PaginationConfig(
                    total_pages_header="X-WP-TotalPages",
                    max_pages=50,
                ),
            ),
        ),
    )

    page1 = [{"id": 1, "name": "A"}]

    base = "https://example.com/api"
    respx.get(base, params={"per_page": "1", "page": "1"}).mock(
        return_value=httpx.Response(200, json=page1, headers={"X-WP-TotalPages": "5", "X-WP-Total": "5"})
    )
    respx.get(base, params={"per_page": "1", "page": "2"}).mock(
        return_value=httpx.Response(200, json=[], headers={"X-WP-TotalPages": "5", "X-WP-Total": "5"})
    )

    snapshot = await scraper.fetch(fuente)

    data = json.loads(snapshot.contenido_crudo)
    assert len(data) == 1  # page 2 was empty, stops early


@pytest.mark.asyncio
async def test_extract_from_paginated_snapshot() -> None:
    scraper = JsonApiScraper()

    fuente = Fuente(
        id=uuid4(),
        nombre="EXTRACT_TEST",
        url_base="https://example.com/",  # type: ignore[arg-type]
        configuracion_reglas=RulesConfig(
            nombre="EXTRACT_TEST",
            url_busqueda="https://example.com/api",  # type: ignore[arg-type]
            estrategia="json_api",
            json_mapping=JsonMappingConfig(
                root_path=None,
                identificador="id",
                titulo="title.rendered",
                link_detalle="link",
                estado="status",
            ),
        ),
    )

    consolidated = [
        {"id": 10, "title": {"rendered": "First"}, "link": "https://a.cl", "status": "publish"},
        {"id": 20, "title": {"rendered": "Second"}, "link": "https://b.cl", "status": "draft"},
    ]

    snapshot = Snapshot(
        fuente_id=fuente.id,
        contenido_crudo=json.dumps(consolidated),
        hash_contenido="hash",
        estado_ejecucion="SUCCESS",
    )

    results = await scraper.extract(snapshot, fuente)
    assert len(results) == 2
    assert results[0]["identificador"] == "10"
    assert results[0]["titulo"] == "First"
    assert results[1]["identificador"] == "20"
