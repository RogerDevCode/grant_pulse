"""
Tests de regresión para selectores CSS y extracción — edge cases.

Cubre: selectores que no matchean nada, attr: selectors con atributo
ausente, contenedores encontrados pero sin datos extraíbles,
HTML malformado, y selector 'self'.
"""

from uuid import uuid4

import pytest

from src.core.domain.entities import Fuente, RulesConfig, SelectorConfig, Snapshot
from src.core.domain.exceptions import ExtractionError
from src.infra.scraping.html_static import HtmlStaticScraper


@pytest.fixture
def fuente_base() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="SELECTOR_TEST",
        url_base="https://ejemplo.com",  # type: ignore
        configuracion_reglas=RulesConfig(
            nombre="SELECTOR_TEST",
            url_busqueda="https://ejemplo.com/fondos",  # type: ignore
            selectores=SelectorConfig(
                contenedor_items="div.item",
                identificador="attr:data-code",
                titulo="h2.title",
                descripcion="p.desc",
                link_detalle="a.link",
                estado="span.status",
            ),
        ),
    )


@pytest.mark.asyncio
async def test_extract_no_containers_returns_empty(fuente_base: Fuente) -> None:
    html = "<html><body><p>No items here</p></body></html>"
    scraper = HtmlStaticScraper()
    snapshot = Snapshot(fuente_id=fuente_base.id, contenido_crudo=html, hash_contenido="h", estado_ejecucion="SUCCESS")

    results = await scraper.extract(snapshot, fuente_base)
    assert results == []


@pytest.mark.asyncio
async def test_extract_containers_but_no_identificador_nor_titulo(fuente_base: Fuente) -> None:
    html = """<html><body>
    <div class="item" data-code="">
        <h2 class="title"></h2>
        <a class="link" href="/detail"></a>
    </div>
    </body></html>"""
    scraper = HtmlStaticScraper()
    snapshot = Snapshot(fuente_id=fuente_base.id, contenido_crudo=html, hash_contenido="h", estado_ejecucion="SUCCESS")

    with pytest.raises(ExtractionError, match="contenedores pero ningún item"):
        await scraper.extract(snapshot, fuente_base)


@pytest.mark.asyncio
async def test_extract_attr_selector_missing_attribute(fuente_base: Fuente) -> None:
    html = """<html><body>
    <div class="item">
        <h2 class="title">Fondo Test</h2>
        <a class="link" href="/detail">Ver</a>
    </div>
    </body></html>"""
    scraper = HtmlStaticScraper()
    snapshot = Snapshot(fuente_id=fuente_base.id, contenido_crudo=html, hash_contenido="h", estado_ejecucion="SUCCESS")

    results = await scraper.extract(snapshot, fuente_base)
    assert len(results) == 1
    assert results[0]["identificador"] is not None
    assert results[0]["identificador"].startswith("hash-")


@pytest.mark.asyncio
async def test_extract_attr_selector_present(fuente_base: Fuente) -> None:
    html = """<html><body>
    <div class="item" data-code="F-2026-001">
        <h2 class="title">Fondo Test</h2>
        <a class="link" href="/detail">Ver</a>
    </div>
    </body></html>"""
    scraper = HtmlStaticScraper()
    snapshot = Snapshot(fuente_id=fuente_base.id, contenido_crudo=html, hash_contenido="h", estado_ejecucion="SUCCESS")

    results = await scraper.extract(snapshot, fuente_base)
    assert len(results) == 1
    assert results[0]["identificador"] == "F-2026-001"


@pytest.mark.asyncio
async def test_extract_malformed_html_still_parses(fuente_base: Fuente) -> None:
    html = """<html><body>
    <div class="item" data-code="X1"><h2 class="title">OK</h2><a class="link" href="/x1">Go</a></div>
    <div class="item" data-code="X2"><h2 class="title">Also OK</h2><a class="link" href="/x2">Go</a>
    </body></html>"""
    scraper = HtmlStaticScraper()
    snapshot = Snapshot(fuente_id=fuente_base.id, contenido_crudo=html, hash_contenido="h", estado_ejecucion="SUCCESS")

    results = await scraper.extract(snapshot, fuente_base)
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_extract_estado_normalizes_values(fuente_base: Fuente) -> None:
    html = """<html><body>
    <div class="item" data-code="E1">
        <h2 class="title">Convocatoria</h2>
        <span class="status">Abierto</span>
        <a class="link" href="/e1">Go</a>
    </div>
    </body></html>"""
    scraper = HtmlStaticScraper()
    snapshot = Snapshot(fuente_id=fuente_base.id, contenido_crudo=html, hash_contenido="h", estado_ejecucion="SUCCESS")

    results = await scraper.extract(snapshot, fuente_base)
    assert results[0]["estado"] == "ABIERTO"


@pytest.mark.asyncio
async def test_extract_no_estado_selector_defaults_desconocido() -> None:
    fuente = Fuente(
        id=uuid4(),
        nombre="NO_ESTADO",
        url_base="https://ejemplo.com",  # type: ignore
        configuracion_reglas=RulesConfig(
            nombre="NO_ESTADO",
            url_busqueda="https://ejemplo.com/fondos",  # type: ignore
            selectores=SelectorConfig(
                contenedor_items="div.item",
                identificador="attr:data-code",
                titulo="h2.title",
                link_detalle="a.link",
                estado=None,
            ),
        ),
    )
    html = """<html><body>
    <div class="item" data-code="N1">
        <h2 class="title">Fondo Sin Estado</h2>
        <a class="link" href="/n1">Go</a>
    </div>
    </body></html>"""
    scraper = HtmlStaticScraper()
    snapshot = Snapshot(fuente_id=fuente.id, contenido_crudo=html, hash_contenido="h", estado_ejecucion="SUCCESS")

    results = await scraper.extract(snapshot, fuente)
    assert results[0]["estado"] == "DESCONOCIDO"
