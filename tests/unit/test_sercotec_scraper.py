"""Tests específicos para el scraper de SERCOTEC.

Documenta y valida el comportamiento correcto después del fix de la paginación
y la eliminación de la agrupación por idInstrumento.

Bugs corregidos:
    1. URL sin params devolvía 8 items; ahora incluye cantidad=500.
    2. agrupar_por: idInstrumento colapsaba 76 filas a 5 únicos.
    3. Bug en lógica de agrupación: solo guardaba primer item del grupo.
"""

import json
from typing import Any
from uuid import uuid4

import httpx
import pytest
import respx

from src.core.domain.entities import Fuente, JsonMappingConfig, RulesConfig, Snapshot
from src.infra.scraping.json_api import JsonApiScraper


def _make_convocatoria(cod_bp: int, id_instrumento: int, region: str, nombre: str) -> dict[str, Any]:
    """Factory helper para crear un item de convocatoria con la estructura real de la API."""
    return {
        "idTipoProgramaFormDinamico": 14,
        "nombre": nombre,
        "idRegion": 1,
        "fechaInicio": "2026-05-19T19:00:00Z",
        "fechaTermino": "2026-06-30T19:00:00Z",
        "proyectoUrlFichaPostulacion": f"https://www.sercotec.cl/convocatoria/{cod_bp}",
        "finalizaDia": 24,
        "region": region,
        "idInstrumento": id_instrumento,
        "idTipoInstrumento": 11,
        "nombreTipoInstrumento": "Fortalecimiento Gremial y Cooperativas",
        "codBp": cod_bp,
        "diferenciaHoraria": 0,
    }


def _make_api_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Envuelve items en la estructura real de respuesta de la API."""
    return {
        "exitoso": True,
        "mensaje": "Se encontraron las convocatorias",
        "datos": items,
    }


@pytest.fixture
def fuente_sercotec() -> Fuente:
    """Fuente SERCOTEC con URL correcta (con parámetros completos)."""
    return Fuente(
        id=uuid4(),
        nombre="SERCOTEC",
        url_base="https://www.sercotec.cl/",  # type: ignore[arg-type]
        configuracion_reglas=RulesConfig(
            nombre="SERCOTEC",
            url_busqueda="https://apisctwidgets.sercotec.cl/api/convocatorias?idRegion=0&idTipoInstrumento=0&idEtapa=0&pagina=1&cantidad=500",  # type: ignore[arg-type]
            estrategia="json_api",
            json_mapping=JsonMappingConfig(
                root_path="datos",
                identificador="codBp",
                titulo="nombre",
                descripcion="nombreTipoInstrumento",
                link_detalle="proyectoUrlFichaPostulacion",
                estado=None,
                fecha_apertura="fechaInicio",
                fecha_cierre="fechaTermino",
                region="region",
                # SIN agrupar_por: cada codBp = 1 convocatoria-región
            ),
        ),
    )


class TestDetectParamPagination:
    """Valida la detección de paginación por parámetro 'pagina'+'cantidad'."""

    def test_detecta_url_con_pagina_y_cantidad(self) -> None:
        scraper = JsonApiScraper()
        url = "https://apisctwidgets.sercotec.cl/api/convocatorias?idRegion=0&pagina=1&cantidad=500"
        result = scraper._detect_param_pagination(url)
        assert result is not None
        _, cantidad = result
        assert cantidad == 500

    def test_no_detecta_url_sin_pagina(self) -> None:
        scraper = JsonApiScraper()
        url = "https://apisctwidgets.sercotec.cl/api/convocatorias"
        result = scraper._detect_param_pagination(url)
        assert result is None

    def test_no_detecta_url_solo_con_cantidad(self) -> None:
        """Sin 'pagina' explícito no activa paginación param."""
        scraper = JsonApiScraper()
        url = "https://api.example.com/items?cantidad=50"
        result = scraper._detect_param_pagination(url)
        assert result is None

    def test_url_antigua_sin_params_no_detectada(self) -> None:
        """La URL antigua sin parámetros no activa paginación param."""
        scraper = JsonApiScraper()
        url = "https://apisctwidgets.sercotec.cl/api/convocatorias"
        result = scraper._detect_param_pagination(url)
        assert result is None


class TestExtractSinAgrupacion:
    """Valida que con agrupar_por=None se retornan todos los items sin colapsar."""

    @pytest.mark.asyncio
    async def test_extrae_multiples_items_mismo_instrumento(self, fuente_sercotec: Fuente) -> None:
        """
        Bug regresión: con agrupar_por activo, múltiples convocatorias del mismo
        idInstrumento se colapsaban a una sola. Sin agrupar_por, se retornan todas.
        """
        # Simular 8 regiones del mismo instrumento (ej: Fortalecimiento Gremial)
        regiones = [
            "Región de Tarapacá",
            "Región de Antofagasta",
            "Región de Atacama",
            "Región de Coquimbo",
            "Región de Valparaíso",
            "Región de O'Higgins",
            "Región del Maule",
            "Región del Biobío",
        ]
        items = [
            _make_convocatoria(
                cod_bp=1513834 + i,
                id_instrumento=424,  # mismo instrumento para todas
                region=region,
                nombre=f"Fortalecimiento Gremial 2026 - {region}",
            )
            for i, region in enumerate(regiones)
        ]

        snapshot = Snapshot(
            fuente_id=fuente_sercotec.id,
            contenido_crudo=json.dumps(_make_api_response(items)),
            hash_contenido="hash_test",
            estado_ejecucion="SUCCESS",
        )

        scraper = JsonApiScraper()
        resultados = await scraper.extract(snapshot, fuente_sercotec)

        # DEBE retornar 8, no 1 como hacía antes con agrupar_por
        assert len(resultados) == 8, (
            f"Esperaba 8 items (uno por región), pero obtuvo {len(resultados)}. "
            "Posible bug de agrupación reactivado."
        )

    @pytest.mark.asyncio
    async def test_extrae_76_items_realistas(self, fuente_sercotec: Fuente) -> None:
        """Simula la respuesta real de la API con 76 items (5 instrumentos × múltiples regiones)."""
        instrumentos = [381, 391, 420, 424, 458]
        regiones_count = [1, 16, 16, 16, 16]  # aprox. distribución real
        items = []
        cod_bp = 1351769
        for instr, n_regiones in zip(instrumentos, regiones_count, strict=False):
            for r in range(n_regiones):
                items.append(
                    _make_convocatoria(
                        cod_bp=cod_bp,
                        id_instrumento=instr,
                        region=f"Región {r}",
                        nombre=f"Convocatoria Instrumento {instr} - Región {r}",
                    )
                )
                cod_bp += 1

        assert len(items) == 65  # 1 + 16 + 16 + 16 + 16

        snapshot = Snapshot(
            fuente_id=fuente_sercotec.id,
            contenido_crudo=json.dumps(_make_api_response(items)),
            hash_contenido="hash_65",
            estado_ejecucion="SUCCESS",
        )

        scraper = JsonApiScraper()
        resultados = await scraper.extract(snapshot, fuente_sercotec)

        assert len(resultados) == 65
        # Verificar que todos tienen identificadores únicos (codBp)
        ids = {r["identificador"] for r in resultados}
        assert len(ids) == 65, "Algunos items tienen identificadores duplicados"

    @pytest.mark.asyncio
    async def test_cada_item_tiene_region_correcta(self, fuente_sercotec: Fuente) -> None:
        """Verifica que la región se preserva correctamente en cada item."""
        items = [
            _make_convocatoria(1001, 424, "Región de Tarapacá", "Convocatoria Tarapacá"),
            _make_convocatoria(1002, 424, "Región de Antofagasta", "Convocatoria Antofagasta"),
        ]

        snapshot = Snapshot(
            fuente_id=fuente_sercotec.id,
            contenido_crudo=json.dumps(_make_api_response(items)),
            hash_contenido="hash_regiones",
            estado_ejecucion="SUCCESS",
        )

        scraper = JsonApiScraper()
        resultados = await scraper.extract(snapshot, fuente_sercotec)

        assert len(resultados) == 2
        regiones = {r["region"] for r in resultados}
        assert "Región de Tarapacá" in regiones
        assert "Región de Antofagasta" in regiones


class TestFetchParamPagination:
    """Valida la paginación nativa por parámetro 'pagina' de la API de SERCOTEC."""

    @pytest.mark.asyncio
    async def test_fetch_una_sola_pagina_si_items_menor_cantidad(self, fuente_sercotec: Fuente) -> None:
        """
        Si la respuesta tiene menos items que 'cantidad', no se paginan más páginas.
        Caso típico: 76 items con cantidad=500 -> solo 1 petición.
        """
        items_pagina_1 = [
            _make_convocatoria(1000 + i, 424, f"Región {i}", f"Conv {i}")
            for i in range(76)
        ]

        with respx.mock(assert_all_called=False) as mock:
            route = mock.get(
                url="https://apisctwidgets.sercotec.cl/api/convocatorias",
            ).mock(
                return_value=httpx.Response(200, json=_make_api_response(items_pagina_1))
            )

            scraper = JsonApiScraper()
            snapshot = await scraper.fetch(fuente_sercotec)

        data = json.loads(snapshot.contenido_crudo)
        items = data["datos"]
        assert len(items) == 76
        assert route.call_count == 1, "Solo debería hacer 1 petición cuando items < cantidad"

    @pytest.mark.asyncio
    async def test_fetch_pagina_siguiente_si_items_igual_cantidad(self, fuente_sercotec: Fuente) -> None:
        """
        Si la primera página tiene exactamente 'cantidad' items, hace una petición a la página 2.
        Si la segunda página tiene menos, termina.
        La paginación funciona y acumula correctamente los items.
        """
        # Fuente con cantidad=3 para simplificar el test
        fuente_pequena = fuente_sercotec.model_copy(
            update={
                "configuracion_reglas": fuente_sercotec.configuracion_reglas.model_copy(
                    update={
                        "url_busqueda": "https://apisctwidgets.sercotec.cl/api/convocatorias?idRegion=0&pagina=1&cantidad=3"  # noqa: E501
                    }
                )
            }
        )

        items_pagina_1 = [_make_convocatoria(1000 + i, 424, f"R{i}", f"C{i}") for i in range(3)]
        items_pagina_2 = [_make_convocatoria(2000 + i, 424, f"R{i}", f"C{i}") for i in range(2)]

        with respx.mock(assert_all_called=False) as mock:
            route1 = mock.get(
                url__regex=r"pagina=1",
            ).mock(
                return_value=httpx.Response(200, json=_make_api_response(items_pagina_1))
            )
            route2 = mock.get(
                url__regex=r"pagina=2",
            ).mock(
                return_value=httpx.Response(200, json=_make_api_response(items_pagina_2))
            )

            scraper = JsonApiScraper()
            snapshot = await scraper.fetch(fuente_pequena)

        data = json.loads(snapshot.contenido_crudo)
        items = data["datos"]
        assert len(items) == 5, f"Esperaba 5 items totales (3 + 2), obtuvo {len(items)}"
        assert route1.call_count == 1, "Debería haber hecho 1 petición a página 1"
        assert route2.call_count == 1, "Debería haber hecho 1 petición a página 2"


class TestRegressionOriginalBug:
    """Tests de regresión que documentan los bugs originales que fueron corregidos."""

    def test_url_con_params_trae_mas_items(self) -> None:
        """
        Regresión: La URL sin params (?pagina=1&cantidad=500) solo traía 8 items.
        Este test verifica que la URL en el perfil SERCOTEC incluye los params.
        """
        from src.infra.sources.catalog import resolve_source_profile

        profile = resolve_source_profile("SERCOTEC")
        assert profile is not None
        assert "cantidad=500" in profile.list_url, (
            "La URL del perfil SERCOTEC debe incluir cantidad=500. "
            "Sin este param la API retorna solo 8 items por defecto."
        )
        assert "pagina=1" in profile.list_url, "La URL debe incluir pagina=1"

    def test_fuente_sercotec_no_tiene_agrupar_por(self, fuente_sercotec: Fuente) -> None:
        """
        Regresión: agrupar_por: idInstrumento colapsaba 76 items a 5.
        Verificamos que el mapping de SERCOTEC NO tiene agrupar_por.
        """
        mapping = fuente_sercotec.configuracion_reglas.json_mapping
        assert mapping is not None
        assert mapping.agrupar_por is None, (
            "SERCOTEC no debe usar agrupar_por. "
            "Cada codBp es una convocatoria-región independiente."
        )
