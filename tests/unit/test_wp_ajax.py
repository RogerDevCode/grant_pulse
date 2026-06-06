"""Tests para el motor de scraping WpAjaxScraper."""

import json
from uuid import uuid4

import pytest

from src.core.domain.entities import Fuente, RulesConfig, SelectorConfig, Snapshot
from src.core.domain.exceptions import ExtractionError
from src.infra.scraping.wp_ajax import (  # pyright: ignore[reportPrivateUsage]
    _AJAXURL_PATTERN,
    _NONCE_PATTERN,
    WpAjaxScraper,
)


@pytest.fixture
def fuente_corfo_ajax() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="CORFO",
        url_base="https://www.corfo.gob.cl/",  # type: ignore[arg-type]
        configuracion_reglas=RulesConfig(
            nombre="CORFO",
            url_busqueda="https://www.corfo.gob.cl/sites/cpp/programasyconvocatorias/",  # type: ignore[arg-type]
            estrategia="wp_ajax",
            selectores=SelectorConfig(
                contenedor_items=".caja-resultados_uno",
                identificador="h4",
                titulo="h4",
                descripcion="p",
                link_detalle="a",
                estado="self",
            ),
        ),
    )


@pytest.fixture
def ajax_page_html() -> str:
    return '''
    <html>
    <head></head>
    <body>
    <script>
    var convocatoriasAjax = {"ajaxurl":"https:\\/\\/www.corfo.gob.cl\\/sites\\/cpp\\/wp-admin\\/admin-ajax.php","nonce":"abc123def","searchParam":"","postType":"convocatoria"};
    </script>
    </body>
    </html>
    '''


@pytest.fixture
def ajax_response_json() -> dict[str, object]:
    return {
        "found": 2,
        "html": '''
        <div class="caja-resultados_uno">
            <div class="contenido-caja_prog">
                <h4>CONCURSO INNOVA REGIÓN 2026</h4>
                <div class="apertura"><h3>Apertura</h3><span>01/06/2026</span></div>
                <div class="cierre"><h3>Cierre</h3><span>13/07/2026</span></div>
                <a href="https://www.corfo.gob.cl/sites/cpp/convocatoria/innova-region-2026/">Ver más</a>
            </div>
        </div>
        <div class="caja-resultados_uno">
            <div class="contenido-caja_prog">
                <h4>PROGRAMA DESARROLLA 2026</h4>
                <div class="apertura"><h3>Apertura</h3><span>15/05/2026</span></div>
                <div class="cierre"><h3>Cierre</h3><span>30/06/2026</span></div>
                <a href="https://www.corfo.gob.cl/sites/cpp/convocatoria/desarrolla-2026/">Ver más</a>
            </div>
        </div>
        ''',
    }


@pytest.mark.asyncio
async def test_wp_ajax_extracts_nonce_from_page(
    ajax_page_html: str,
) -> None:
    nonce_match = _NONCE_PATTERN.search(ajax_page_html)
    assert nonce_match is not None
    assert nonce_match.group(1) == "abc123def"

    ajaxurl_match = _AJAXURL_PATTERN.search(ajax_page_html)
    assert ajaxurl_match is not None
    raw_url = ajaxurl_match.group(1)
    assert "admin-ajax.php" in raw_url
    cleaned = raw_url.replace("\\/", "/")
    assert cleaned == "https://www.corfo.gob.cl/sites/cpp/wp-admin/admin-ajax.php"


@pytest.mark.asyncio
async def test_wp_ajax_extract_parses_json_html_response(
    fuente_corfo_ajax: Fuente, ajax_response_json: dict[str, object]
) -> None:
    scraper = WpAjaxScraper()
    combined_content = json.dumps({"metadata": {}, "html": ajax_response_json["html"]})
    snapshot = Snapshot(
        fuente_id=fuente_corfo_ajax.id,
        contenido_crudo=combined_content,
        hash_contenido="testhash",
        estado_ejecucion="SUCCESS",
    )

    items = await scraper.extract(snapshot, fuente_corfo_ajax)
    assert len(items) == 2
    assert items[0]["titulo"] == "CONCURSO INNOVA REGIÓN 2026"
    assert items[0]["url_detalle"] == "https://www.corfo.gob.cl/sites/cpp/convocatoria/innova-region-2026/"
    assert items[1]["titulo"] == "PROGRAMA DESARROLLA 2026"


@pytest.mark.asyncio
async def test_wp_ajax_extract_handles_plain_html_fallback(
    fuente_corfo_ajax: Fuente, ajax_response_json: dict[str, object]
) -> None:
    scraper = WpAjaxScraper()
    snapshot = Snapshot(
        fuente_id=fuente_corfo_ajax.id,
        contenido_crudo=str(ajax_response_json["html"]),
        hash_contenido="testhash",
        estado_ejecucion="SUCCESS",
    )

    items = await scraper.extract(snapshot, fuente_corfo_ajax)
    assert len(items) == 2


@pytest.mark.asyncio
async def test_wp_ajax_extract_returns_empty_when_no_items(fuente_corfo_ajax: Fuente) -> None:
    scraper = WpAjaxScraper()
    combined_content = json.dumps({"metadata": {}, "html": "<div>No items</div>"})
    snapshot = Snapshot(
        fuente_id=fuente_corfo_ajax.id,
        contenido_crudo=combined_content,
        hash_contenido="testhash",
        estado_ejecucion="SUCCESS",
    )

    items = await scraper.extract(snapshot, fuente_corfo_ajax)
    assert items == []


@pytest.mark.asyncio
async def test_wp_ajax_extract_raises_when_containers_found_but_empty(fuente_corfo_ajax: Fuente) -> None:
    scraper = WpAjaxScraper()
    html_with_empty_containers = '<div class="caja-resultados_uno"><p>empty</p></div>'
    combined_content = json.dumps({"metadata": {}, "html": html_with_empty_containers})
    snapshot = Snapshot(
        fuente_id=fuente_corfo_ajax.id,
        contenido_crudo=combined_content,
        hash_contenido="testhash",
        estado_ejecucion="SUCCESS",
    )

    with pytest.raises(ExtractionError, match="ningún item pudo ser extraído"):
        await scraper.extract(snapshot, fuente_corfo_ajax)


@pytest.mark.asyncio
async def test_wp_ajax_extract_raises_when_no_selectors() -> None:
    fuente = Fuente(
        id=uuid4(),
        nombre="TEST_WP_AJAX",
        url_base="https://example.com/",  # type: ignore[arg-type]
        configuracion_reglas=RulesConfig(
            nombre="TEST_WP_AJAX",
            url_busqueda="https://example.com/page/",  # type: ignore[arg-type]
            estrategia="wp_ajax",
        ),
    )
    scraper = WpAjaxScraper()
    snapshot = Snapshot(
        fuente_id=fuente.id,
        contenido_crudo='{"html": "<div>test</div>"}',
        hash_contenido="testhash",
        estado_ejecucion="SUCCESS",
    )

    with pytest.raises(ExtractionError, match="No se han configurado selectores"):
        await scraper.extract(snapshot, fuente)
