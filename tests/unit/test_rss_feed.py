"""Tests para el motor de scraping RssFeedScraper."""

from uuid import uuid4

import pytest

from src.core.domain.entities import Fuente, RulesConfig, SelectorConfig, Snapshot
from src.core.domain.exceptions import ExtractionError
from src.infra.scraping.rss_feed import RssFeedScraper


@pytest.fixture
def fuente_anid_rss() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="ANID",
        url_base="https://anid.cl/",  # type: ignore[arg-type]
        configuracion_reglas=RulesConfig(
            nombre="ANID",
            url_busqueda="https://anid.cl/feed/",  # type: ignore[arg-type]
            estrategia="rss_feed",
            selectores=SelectorConfig(
                contenedor_items="item",
                identificador="link",
                titulo="title",
                descripcion="description",
                link_detalle="link",
                estado="self",
            ),
        ),
    )


@pytest.fixture
def rss_feed_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
    <title>ANID</title>
    <link>https://anid.cl</link>
    <item>
        <title>Concurso FONDECYT 2026 está ABIERTO para postulaciones</title>
        <link>https://anid.cl/concursos/fondecyt-2026/</link>
        <description>Se abre convocatoria FONDECYT con cierre el 15 de agosto de 2026.</description>
        <pubDate>Mon, 01 Jun 2026 12:00:00 +0000</pubDate>
    </item>
    <item>
        <title>Concurso FONDAP 2026 CERRADO</title>
        <link>https://anid.cl/concursos/fondap-2026/</link>
        <description>El concurso FONDAP 2026 ha finalizado.</description>
        <pubDate>Sun, 01 Jun 2026 10:00:00 +0000</pubDate>
    </item>
    <item>
        <title>Reunión de directores</title>
        <link>https://anid.cl/noticias/reunion/</link>
        <description>Una reunión administrativa sobre organización interna.</description>
        <pubDate>Sat, 31 May 2026 08:00:00 +0000</pubDate>
    </item>
</channel>
</rss>"""


@pytest.fixture
def atom_feed_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
    <title>FIA Feed</title>
    <link href="https://www.fia.cl/feed/"/>
    <entry>
        <title>FIA abre convocatoria nacional de Proyectos de Innovación 2026</title>
        <link href="https://www.fia.cl/convocatorias/proyectos-2026/"/>
        <summary>Convocatoria ABIERTA hasta el 25/06/2026. Monto máximo $150.000.000 CLP.</summary>
        <published>2026-05-27T19:00:00Z</published>
    </entry>
    <entry>
        <title>Evento académico</title>
        <link href="https://www.fia.cl/eventos/academia/"/>
        <summary>Charla académica sobre historia.</summary>
        <published>2026-05-20T16:00:00Z</published>
    </entry>
</feed>"""


@pytest.mark.asyncio
async def test_rss_feed_extract_filters_convocatorias(
    fuente_anid_rss: Fuente, rss_feed_xml: str
) -> None:
    scraper = RssFeedScraper()
    snapshot = Snapshot(
        fuente_id=fuente_anid_rss.id,
        contenido_crudo=rss_feed_xml,
        hash_contenido="testhash",
        estado_ejecucion="SUCCESS",
    )

    items = await scraper.extract(snapshot, fuente_anid_rss)
    assert len(items) == 2
    assert items[0]["titulo"] == "Concurso FONDECYT 2026 está ABIERTO para postulaciones"
    assert items[0]["estado"] == "ABIERTO"
    assert items[1]["estado"] == "CERRADO"


@pytest.mark.asyncio
async def test_rss_feed_extract_detects_fecha_cierre(fuente_anid_rss: Fuente) -> None:
    feed_with_date = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test</title>
<item>
    <title>Convocatoria FONDECYT ABIERTA</title>
    <link>https://anid.cl/c/1/</link>
    <description>Postulaciones hasta el 15 de agosto de 2026.</description>
</item>
</channel></rss>"""

    scraper = RssFeedScraper()
    snapshot = Snapshot(
        fuente_id=fuente_anid_rss.id,
        contenido_crudo=feed_with_date,
        hash_contenido="testhash",
        estado_ejecucion="SUCCESS",
    )

    items = await scraper.extract(snapshot, fuente_anid_rss)
    assert len(items) == 1
    assert items[0]["fecha_cierre"] is not None
    assert "agosto" in items[0]["fecha_cierre"].lower() or "2026" in items[0]["fecha_cierre"]


@pytest.mark.asyncio
async def test_rss_feed_extract_detects_monto(fuente_anid_rss: Fuente) -> None:
    feed_with_amount = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test</title>
<item>
    <title>Convocatoria Fondo de Innovación ABIERTA</title>
    <link>https://anid.cl/c/2/</link>
    <description>Financiamiento de $150.000.000 CLP para proyectos de innovación.</description>
</item>
</channel></rss>"""

    scraper = RssFeedScraper()
    snapshot = Snapshot(
        fuente_id=fuente_anid_rss.id,
        contenido_crudo=feed_with_amount,
        hash_contenido="testhash",
        estado_ejecucion="SUCCESS",
    )

    items = await scraper.extract(snapshot, fuente_anid_rss)
    assert len(items) == 1
    assert items[0]["monto"] is not None
    assert "$" in items[0]["monto"]


@pytest.mark.asyncio
async def test_rss_feed_extract_handles_atom_feed(
    fuente_anid_rss: Fuente, atom_feed_xml: str
) -> None:
    scraper = RssFeedScraper()
    snapshot = Snapshot(
        fuente_id=fuente_anid_rss.id,
        contenido_crudo=atom_feed_xml,
        hash_contenido="testhash",
        estado_ejecucion="SUCCESS",
    )

    items = await scraper.extract(snapshot, fuente_anid_rss)
    assert len(items) == 1
    assert items[0]["titulo"] == "FIA abre convocatoria nacional de Proyectos de Innovación 2026"
    assert items[0]["estado"] == "ABIERTO"


@pytest.mark.asyncio
async def test_rss_feed_extract_raises_on_invalid_xml(fuente_anid_rss: Fuente) -> None:
    scraper = RssFeedScraper()
    snapshot = Snapshot(
        fuente_id=fuente_anid_rss.id,
        contenido_crudo="this is not xml",
        hash_contenido="testhash",
        estado_ejecucion="SUCCESS",
    )

    with pytest.raises(ExtractionError, match="Error parseando XML"):
        await scraper.extract(snapshot, fuente_anid_rss)


@pytest.mark.asyncio
async def test_rss_feed_extract_raises_on_non_feed_xml(fuente_anid_rss: Fuente) -> None:
    scraper = RssFeedScraper()
    snapshot = Snapshot(
        fuente_id=fuente_anid_rss.id,
        contenido_crudo='<html><body><p>Not a feed</p></body></html>',
        hash_contenido="testhash",
        estado_ejecucion="SUCCESS",
    )

    with pytest.raises(ExtractionError, match="no es un feed RSS/Atom"):
        await scraper.extract(snapshot, fuente_anid_rss)


@pytest.mark.asyncio
async def test_rss_feed_extract_respects_max_items(fuente_anid_rss: Fuente) -> None:
    many_items_feed = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test</title>"""
    for i in range(20):
        many_items_feed += f"""
<item>
    <title>Convocatoria #{i} ABIERTA</title>
    <link>https://example.com/c/{i}/</link>
    <description>Programa de financiamiento #{i}</description>
</item>"""
    many_items_feed += "</channel></rss>"

    scraper = RssFeedScraper(max_items=5)
    snapshot = Snapshot(
        fuente_id=fuente_anid_rss.id,
        contenido_crudo=many_items_feed,
        hash_contenido="testhash",
        estado_ejecucion="SUCCESS",
    )

    items = await scraper.extract(snapshot, fuente_anid_rss)
    assert len(items) == 5


def test_detect_status_patterns() -> None:
    scraper = RssFeedScraper()
    assert scraper._detect_status("Convocatoria ABIERTA") == "ABIERTO"
    assert scraper._detect_status("El concurso está CERRADO") == "CERRADO"
    assert scraper._detect_status("PRÓXIMAMENTE abrirá") == "PROXIMAMENTE"
    assert scraper._detect_status("Postulación abierta") == "ABIERTO"
    assert scraper._detect_status("Sin estado conocido") == "DESCONOCIDO"


def test_is_convocatoria_relevant() -> None:
    scraper = RssFeedScraper()
    assert scraper._is_convocatoria_relevant("Convocatoria FONDECYT 2026", "") is True
    assert scraper._is_convocatoria_relevant("Fondo de Innovación ABIERTO", "") is True
    assert scraper._is_convocatoria_relevant("Reunión de directores", "") is False
    assert scraper._is_convocatoria_relevant("", "Charla académica sobre historia") is False
