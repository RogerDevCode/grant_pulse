"""Tests unitarios para SubdereHomepageScraper."""

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from src.core.domain.entities import Fuente, RulesConfig, Snapshot
from src.core.domain.exceptions import NetworkError
from src.infra.scraping.subdere_homepage import SubdereHomepageScraper


def _make_fuente() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="SUBDERE",
        url_base="https://www.subdere.gob.cl/",  # type: ignore[arg-type]
        configuracion_reglas=RulesConfig(
            nombre="SUBDERE",
            url_busqueda="https://www.subdere.gob.cl/",  # type: ignore[arg-type]
            estrategia="subdere_homepage",
        ),
    )


_FAKE_HOMEPAGE = """\
<!DOCTYPE html>
<html lang="es">
<head><title>SUBDERE</title></head>
<body>
<div class="views-slideshow-cycle-main-frame-row">
  <a href="/sala-de-prensa/rancagua-se-incorpora-al-programa-revive-barrios">
    Rancagua se incorpora al programa Revive Barrios para impulsar su recuperación patrimonial
  </a>
  <span>Sábado, 30 Mayo 2026</span>
  <p>El acuerdo permitirá avanzar en iniciativas orientadas a rescatar inmuebles patrimoniales.</p>
</div>
<div class="views-slideshow-cycle-main-frame-row">
  <a href="/sala-de-prensa/noticia-no-relacionada">
    Subsecretario inaugura evento cultural en la comuna de Punitaqui
  </a>
  <span>Viernes, 29 Mayo 2026</span>
  <p>Un evento cultural con música y danza.</p>
</div>
<div class="view-noticias-subdere">
  <div class="views-row">
    <a href="/sala-de-prensa/subdere-fondo-apoyo-contingencia">
      Subdere y Gobierno Regional realizan jornada de inducción al Fondo de Apoyo a la Contingencia Regional
    </a>
    <span>Junio 02, 2026</span>
    <p>La instancia técnica tuvo como objetivo optimizar la formulación y ejecución.</p>
  </div>
</div>
<div class="enlace">
  <a href="/programas/divisi%C3%B3n-municipalidades/programa-mejoramiento-urbano-y-equipamiento-comunal-pmu">
    Programa de Mejoramiento Urbano PMU
  </a>
  <a href="/programas/divisi%C3%B3n-municipalidades/programa-mejoramiento-de-barrios-pmb">
    Programa de Mejoramiento de Barrios PMB
  </a>
  <a href="/programas/division_desarrollo_regional">
    División Desarrollo Regional
  </a>
</div>
</body>
</html>
"""


class TestSubdereHomepageScraperExtract:
    """Tests para la extracción de items desde la homepage."""

    @pytest.mark.asyncio
    async def test_extracts_relevant_news_items(self) -> None:
        scraper = SubdereHomepageScraper()
        fuente = _make_fuente()
        snapshot = Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=_FAKE_HOMEPAGE,
            hash_contenido=hashlib.sha256(_FAKE_HOMEPAGE.encode()).hexdigest(),
            estado_ejecucion="SUCCESS",
        )
        results = await scraper.extract(snapshot, fuente)

        ids = {r["identificador"] for r in results}
        assert "rancagua-se-incorpora-al-programa-revive-barrios" in ids
        assert "subdere-fondo-apoyo-contingencia" in ids

    @pytest.mark.asyncio
    async def test_filters_irrelevant_news(self) -> None:
        scraper = SubdereHomepageScraper()
        fuente = _make_fuente()
        snapshot = Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=_FAKE_HOMEPAGE,
            hash_contenido=hashlib.sha256(_FAKE_HOMEPAGE.encode()).hexdigest(),
            estado_ejecucion="SUCCESS",
        )
        results = await scraper.extract(snapshot, fuente)
        titles = [r["titulo"] for r in results]
        assert not any("evento cultural" in (t or "").lower() for t in titles)

    @pytest.mark.asyncio
    async def test_extracts_featured_programs(self) -> None:
        scraper = SubdereHomepageScraper()
        fuente = _make_fuente()
        snapshot = Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=_FAKE_HOMEPAGE,
            hash_contenido=hashlib.sha256(_FAKE_HOMEPAGE.encode()).hexdigest(),
            estado_ejecucion="SUCCESS",
        )
        results = await scraper.extract(snapshot, fuente)
        ids = {r["identificador"] for r in results}
        assert "programa-mejoramiento-urbano-y-equipamiento-comunal-pmu" in ids
        assert "programa-mejoramiento-de-barrios-pmb" in ids

    @pytest.mark.asyncio
    async def test_skips_division_links(self) -> None:
        scraper = SubdereHomepageScraper()
        fuente = _make_fuente()
        snapshot = Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=_FAKE_HOMEPAGE,
            hash_contenido=hashlib.sha256(_FAKE_HOMEPAGE.encode()).hexdigest(),
            estado_ejecucion="SUCCESS",
        )
        results = await scraper.extract(snapshot, fuente)
        ids = {r["identificador"] for r in results}
        assert "division_desarrollo_regional" not in ids

    @pytest.mark.asyncio
    async def test_news_items_have_valid_urls(self) -> None:
        scraper = SubdereHomepageScraper()
        fuente = _make_fuente()
        snapshot = Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=_FAKE_HOMEPAGE,
            hash_contenido=hashlib.sha256(_FAKE_HOMEPAGE.encode()).hexdigest(),
            estado_ejecucion="SUCCESS",
        )
        results = await scraper.extract(snapshot, fuente)
        for r in results:
            assert r["url_detalle"] is not None
            assert r["url_detalle"].startswith("https://www.subdere.gob.cl/")

    @pytest.mark.asyncio
    async def test_all_items_have_required_fields(self) -> None:
        scraper = SubdereHomepageScraper()
        fuente = _make_fuente()
        snapshot = Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=_FAKE_HOMEPAGE,
            hash_contenido=hashlib.sha256(_FAKE_HOMEPAGE.encode()).hexdigest(),
            estado_ejecucion="SUCCESS",
        )
        results = await scraper.extract(snapshot, fuente)
        required_keys = {"identificador", "titulo", "url_detalle", "estado"}
        for r in results:
            assert required_keys.issubset(r.keys())
            assert r["identificador"] is not None
            assert r["titulo"] is not None
            assert r["url_detalle"] is not None

    @pytest.mark.asyncio
    async def test_empty_html_returns_empty_list(self) -> None:
        scraper = SubdereHomepageScraper()
        fuente = _make_fuente()
        empty_html = "<html><body></body></html>"
        snapshot = Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=empty_html,
            hash_contenido=hashlib.sha256(empty_html.encode()).hexdigest(),
            estado_ejecucion="SUCCESS",
        )
        results = await scraper.extract(snapshot, fuente)
        assert results == []

    @pytest.mark.asyncio
    async def test_deduplicates_by_href(self) -> None:
        scraper = SubdereHomepageScraper()
        fuente = _make_fuente()
        dup_html = """\
<html><body>
<a href="/sala-de-prensa/programa-revive-barrios">Programa Revive Barrios para impulsar la recuperación</a>
<a href="/sala-de-prensa/programa-revive-barrios">Programa Revive Barrios para impulsar la recuperación</a>
</body></html>
"""
        snapshot = Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=dup_html,
            hash_contenido=hashlib.sha256(dup_html.encode()).hexdigest(),
            estado_ejecucion="SUCCESS",
        )
        results = await scraper.extract(snapshot, fuente)
        hrefs = [r["url_detalle"] for r in results]
        assert len(hrefs) == len(set(hrefs))


class TestSubdereHomepageScraperFetch:
    """Tests para el fetch con mocks HTTP."""

    @pytest.mark.asyncio
    async def test_fetch_returns_snapshot_on_200(self) -> None:
        scraper = SubdereHomepageScraper()
        fuente = _make_fuente()

        import respx

        with respx.mock:
            respx.get("https://www.subdere.gob.cl/").mock(
                return_value=httpx.Response(200, text=_FAKE_HOMEPAGE)
            )
            snapshot = await scraper.fetch(fuente)
            assert snapshot.estado_ejecucion == "SUCCESS"
            assert snapshot.contenido_crudo == _FAKE_HOMEPAGE
            assert snapshot.hash_contenido == hashlib.sha256(_FAKE_HOMEPAGE.encode()).hexdigest()

    @pytest.mark.asyncio
    async def test_fetch_raises_network_error_on_403(self) -> None:
        scraper = SubdereHomepageScraper()
        fuente = _make_fuente()

        import respx

        with respx.mock:
            respx.get("https://www.subdere.gob.cl/").mock(
                return_value=httpx.Response(403, text="Forbidden")
            )
            with pytest.raises(NetworkError, match="403"):
                await scraper.fetch(fuente)

    @pytest.mark.asyncio
    async def test_fetch_raises_network_error_on_connection_error(self) -> None:
        scraper = SubdereHomepageScraper()
        fuente = _make_fuente()

        import respx

        with respx.mock:
            respx.get("https://www.subdere.gob.cl/").mock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            with pytest.raises(NetworkError, match="Error de red"):
                await scraper.fetch(fuente)
