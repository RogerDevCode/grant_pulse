"""Unit tests para FosisMultiPageScraper."""

from uuid import uuid4

import pytest

from src.core.domain.entities import Fuente, RulesConfig
from src.core.domain.exceptions import NetworkError
from src.infra.scraping.fosis_multipage import FosisMultiPageScraper


def _make_fuente() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="FOSIS",
        url_base="https://www.fosis.gob.cl/",  # type: ignore[arg-type]
        configuracion_reglas=RulesConfig(
            nombre="FOSIS",
            url_busqueda="https://www.fosis.gob.cl/es/programas/autonomia-economica/",  # type: ignore[arg-type]
            estrategia="fosis_multipage",
        ),
    )


_FAKE_PROGRAM_PAGE = """<html><body>
<div style="background-color: #f0f0f0">
  <h2>Emprendamos Semilla</h2>
  <p>Programa de emprendimiento para iniciantes</p>
  <a class="btn" href="/es/programas/autonomia-economica/emprendamos-semilla/">Ver más</a>
</div>
<div style="background-color: #f0f0f0">
  <h2>Emprendamos</h2>
  <p>Programa de emprendimiento para negocios en funcionamiento</p>
  <a class="btn" href="/es/programas/autonomia-economica/emprendamos/">Ver más</a>
</div>
<div style="background-color: #f0f0f0">
  <h2>FAQ Section</h2>
  <p>Preguntas frecuentes</p>
</div>
</body></html>"""

_FAKE_ALIANZAS_PAGE = """<html><body>
<a href="/es/convocatoria-alianzas/ambito-comercio/">Llamado abierto a instituciones vinculadas a organismos del sector privado</a>
<a href="/es/convocatoria-alianzas/ambito-capacitacion/">Llamado abierto a instituciones vinculadas al ámbito capacitación</a>
<a href="/es/convocatoria-alianzas/">Página principal</a>
<a href="/es/convocatoria-alianzas/ambito-corto">Corto</a>
<a href="https://app-sa.readspeaker.com/test">Readspeaker</a>
</body></html>"""


class TestCombineSplitRoundtrip:
    def test_roundtrip_preserves_page_names(self) -> None:
        scraper = FosisMultiPageScraper()
        pages = {
            "autonomia-economica": "<html>test1</html>",
            "autonomia-desarrollo": "<html>test2</html>",
            "habitabilidad": "<html>test3</html>",
            "innova-fosis": "<html>test4</html>",
            "convocatoria-alianzas": "<html>test5</html>",
        }
        combined = scraper._combine_pages(pages)
        result = scraper._split_pages(combined)
        assert set(result.keys()) == set(pages.keys())
        for key in pages:
            assert result[key] == pages[key]

    def test_split_handles_empty_content(self) -> None:
        scraper = FosisMultiPageScraper()
        pages = scraper._split_pages("")
        assert pages == {}


class TestExtractPrograms:
    @pytest.mark.asyncio
    async def test_extracts_programs_with_h2_and_btn(self) -> None:
        scraper = FosisMultiPageScraper()
        fuente = _make_fuente()

        pages = {
            "autonomia-economica": _FAKE_PROGRAM_PAGE,
            "autonomia-desarrollo": "<html><body></body></html>",
            "habitabilidad": "<html><body></body></html>",
            "innova-fosis": "<html><body></body></html>",
            "convocatoria-alianzas": "<html><body></body></html>",
        }
        combined = scraper._combine_pages(pages)
        import hashlib
        from datetime import UTC, datetime

        from src.core.domain.entities import Snapshot

        snapshot = Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=combined,
            hash_contenido=hashlib.sha256(combined.encode()).hexdigest(),
            estado_ejecucion="SUCCESS",
        )

        items = await scraper.extract(snapshot, fuente)
        assert len(items) == 2
        assert items[0]["titulo"] == "Emprendamos Semilla"
        assert items[0]["identificador"] == "emprendamos-semilla"
        assert items[1]["titulo"] == "Emprendamos"

    @pytest.mark.asyncio
    async def test_deduplicates_by_url(self) -> None:
        scraper = FosisMultiPageScraper()
        fuente = _make_fuente()

        same_program = """<html><body>
<div style="background-color: #f0f0f0">
  <h2>Emprendamos Semilla</h2>
  <p>Otra categoría</p>
  <a class="btn" href="/es/programas/autonomia-economica/emprendamos-semilla/">Ver más</a>
</div>
</body></html>"""

        pages = {
            "autonomia-economica": _FAKE_PROGRAM_PAGE,
            "autonomia-desarrollo": same_program,
            "habitabilidad": "<html><body></body></html>",
            "innova-fosis": "<html><body></body></html>",
            "convocatoria-alianzas": "<html><body></body></html>",
        }
        combined = scraper._combine_pages(pages)
        import hashlib
        from datetime import UTC, datetime

        from src.core.domain.entities import Snapshot

        snapshot = Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=combined,
            hash_contenido=hashlib.sha256(combined.encode()).hexdigest(),
            estado_ejecucion="SUCCESS",
        )

        items = await scraper.extract(snapshot, fuente)
        emprendamos = [i for i in items if i["identificador"] == "emprendamos-semilla"]
        assert len(emprendamos) == 1


class TestExtractAlianzas:
    @pytest.mark.asyncio
    async def test_extracts_alianzas_links(self) -> None:
        scraper = FosisMultiPageScraper()
        fuente = _make_fuente()

        pages = {
            "autonomia-economica": "<html><body></body></html>",
            "autonomia-desarrollo": "<html><body></body></html>",
            "habitabilidad": "<html><body></body></html>",
            "innova-fosis": "<html><body></body></html>",
            "convocatoria-alianzas": _FAKE_ALIANZAS_PAGE,
        }
        combined = scraper._combine_pages(pages)
        import hashlib
        from datetime import UTC, datetime

        from src.core.domain.entities import Snapshot

        snapshot = Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=combined,
            hash_contenido=hashlib.sha256(combined.encode()).hexdigest(),
            estado_ejecucion="SUCCESS",
        )

        items = await scraper.extract(snapshot, fuente)
        alianzas = [i for i in items if i["identificador"].startswith("alianza-")]
        assert len(alianzas) == 2
        assert alianzas[0]["identificador"] == "alianza-ambito-comercio"
        assert alianzas[1]["identificador"] == "alianza-ambito-capacitacion"


class TestFetchWithMockedHttpx:
    @pytest.mark.asyncio
    async def test_fetch_raises_network_error_on_http_error(self) -> None:
        import respx

        scraper = FosisMultiPageScraper()
        fuente = _make_fuente()

        with respx.mock:
            respx.get("https://www.fosis.gob.cl/es/programas/autonomia-economica/").respond(500)
            with pytest.raises(NetworkError):
                await scraper.fetch(fuente)
