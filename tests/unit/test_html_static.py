"""
Tests unitarios para el módulo de scraping estático.
"""

from uuid import uuid4

import pytest
import respx
from httpx import Response

from src.core.domain.entities import (
    Fuente,
    RulesConfig,
    SelectorConfig,
    Snapshot,
)
from src.core.domain.exceptions import NetworkError
from src.infra.scraping.html_static import HtmlStaticScraper


@pytest.fixture
def mock_fuente() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="Test Fuente",
        url_base="https://ejemplo.com",  # type: ignore
        configuracion_reglas=RulesConfig(
            nombre="Test",
            url_busqueda="https://ejemplo.com/fondos",  # type: ignore
            selectores=SelectorConfig(
                contenedor_items="div.item",
                identificador="attr:data-id",
                titulo="h2.title",
                descripcion="p.desc",
                link_detalle="a.link",
                estado="span.status",
                fecha_cierre="span.date",
                monto="span.amount",
            ),
        ),
    )


@pytest.fixture
def mock_html() -> str:
    return """
    <html>
        <body>
            <div class="item" data-id="F001">
                <h2 class="title">Fondo Semilla</h2>
                <p class="desc">Apoyo a emprendedores</p>
                <a class="link" href="/fondos/F001">Ver más</a>
                <span class="status">ABIERTO</span>
                <span class="date">31/12/2026</span>
                <span class="amount">$10.000.000</span>
            </div>
            <div class="item" data-id="F002">
                <h2 class="title">Fondo Crecimiento</h2>
                <p class="desc">Para empresas consolidadas</p>
                <a class="link" href="/fondos/F002">Ver más</a>
                <span class="status">CERRADO</span>
            </div>
        </body>
    </html>
    """


@pytest.mark.asyncio
async def test_html_static_fetch_success(mock_fuente: Fuente, mock_html: str) -> None:
    """Verifica que el scraper descargue correctamente el HTML crudo."""
    scraper = HtmlStaticScraper()
    url = str(mock_fuente.configuracion_reglas.url_busqueda)

    with respx.mock(assert_all_called=True) as mocker:
        mocker.get(url).mock(return_value=Response(200, text=mock_html))

        snapshot = await scraper.fetch(mock_fuente)

        assert snapshot is not None
        assert snapshot.fuente_id == mock_fuente.id
        assert snapshot.estado_ejecucion == "SUCCESS"
        assert snapshot.contenido_crudo == mock_html


@pytest.mark.asyncio
async def test_html_static_fetch_network_error(mock_fuente: Fuente) -> None:
    """Verifica el fail-fast del scraper ante errores HTTP (e.g. 500)."""
    scraper = HtmlStaticScraper()
    url = str(mock_fuente.configuracion_reglas.url_busqueda)

    with respx.mock(assert_all_called=True) as mocker:
        mocker.get(url).mock(return_value=Response(500, text="Internal Server Error"))

        with pytest.raises(NetworkError) as exc_info:
            await scraper.fetch(mock_fuente)

        assert "Error HTTP 500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_html_static_extract_success(mock_fuente: Fuente, mock_html: str) -> None:
    """Verifica que los datos se extraigan correctamente siguiendo los selectores."""
    scraper = HtmlStaticScraper()
    snapshot = Snapshot(
        fuente_id=mock_fuente.id, contenido_crudo=mock_html, hash_contenido="dummy_hash", estado_ejecucion="SUCCESS"
    )

    resultados = await scraper.extract(snapshot, mock_fuente)

    assert len(resultados) == 2

    # Primer item completo
    assert resultados[0]["identificador"] == "F001"
    assert resultados[0]["titulo"] == "Fondo Semilla"
    assert resultados[0]["descripcion"] == "Apoyo a emprendedores"
    assert resultados[0]["url_detalle"] == "https://ejemplo.com/fondos/F001"
    assert resultados[0]["estado"] == "ABIERTO"
    assert resultados[0]["fecha_cierre"] == "31/12/2026"
    assert resultados[0]["monto"] == "$10.000.000"

    # Segundo item parcial
    assert resultados[1]["identificador"] == "F002"
    assert resultados[1]["fecha_cierre"] is None
    assert resultados[1]["monto"] is None


@pytest.mark.asyncio
async def test_html_static_with_normalizers(mock_fuente: Fuente) -> None:
    """Verifica que el motor aplica correctamente expresiones regulares de Normalizadores."""
    from src.core.domain.entities import NormalizerConfig, NormalizerItem

    mock_fuente.configuracion_reglas.normalizadores = NormalizerConfig(
        fecha_cierre=NormalizerItem(regex_extraction=r"cierra el (\d{2}/\d{2}/\d{4})"),
        monto=NormalizerItem(regex_extraction=r"Monto: (\d+) CLP"),
    )

    html = """
    <html><body><div class="item" data-id="X001">
        <h2 class="title">Test</h2>
        <a class="link" href="/concurso/1">Ver</a>
        <span class="status">Abierto</span>
        <span class="date">Atención: cierra el 01/05/2026 sin prórroga</span>
        <span class="amount">El Monto: 500000 CLP exactos</span>
    </div></body></html>
    """
    scraper = HtmlStaticScraper()
    snapshot = Snapshot(
        fuente_id=mock_fuente.id, contenido_crudo=html, hash_contenido="dummy", estado_ejecucion="SUCCESS"
    )

    resultados = await scraper.extract(snapshot, mock_fuente)
    assert len(resultados) == 1
    assert resultados[0]["fecha_cierre"] == "01/05/2026"
    assert resultados[0]["monto"] == "500000"
    assert resultados[0]["url_detalle"] == "https://ejemplo.com/concurso/1"
