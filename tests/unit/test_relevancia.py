"""Tests para el filtro de relevancia de convocatorias."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import HttpUrl

from src.core.domain.entities import Convocatoria
from src.core.domain.relevancia import (
    es_fecha_titulo_reciente,
    es_financiamiento_proyecto,
    filtrar_relevantes,
    filtrar_relevantes_raw,
)


def _conv(titulo: str = "Fondo de Innovación", descripcion: str | None = None) -> Convocatoria:
    return Convocatoria(
        fuente_id=uuid4(),
        identificador_externo="test-rel-1",
        titulo=titulo,
        url_detalle=HttpUrl("https://example.com/test/"),
        estado="ABIERTO",
        descripcion=descripcion,
    )


class TestEsFinanciamientoProyecto:
    def test_fondo_es_relevante(self) -> None:
        assert es_financiamiento_proyecto("Fondo de Innovación 2026") is True

    def test_subsidio_es_relevante(self) -> None:
        assert es_financiamiento_proyecto("Subsidio Semilla Inicia") is True

    def test_convocatoria_de_fondos_es_relevante(self) -> None:
        assert es_financiamiento_proyecto("Convocatoria de Fondos CORFO") is True

    def test_beca_investigacion_es_relevante(self) -> None:
        assert es_financiamiento_proyecto("Beca de Investigación ANID") is True

    def test_licitacion_publica_no_relevante(self) -> None:
        assert es_financiamiento_proyecto("Licitación Pública N° 123") is False

    def test_compra_equipo_no_relevante(self) -> None:
        assert es_financiamiento_proyecto("Compra de Equipo de Cómputo") is False

    def test_viatico_no_relevante(self) -> None:
        assert es_financiamiento_proyecto("Viático Comisión Servicio") is False

    def test_resolucion_adjudica_no_relevante(self) -> None:
        assert es_financiamiento_proyecto("Resolución Exenta N° 456 Adjudica") is False

    def test_acta_recepcion_no_relevante(self) -> None:
        assert es_financiamiento_proyecto("Acta de Recepción de Ofertas") is False

    def test_contratacion_consultoria_no_relevante(self) -> None:
        assert es_financiamiento_proyecto("Contratación de Consultoría Externa") is False

    def test_declaracion_jurada_no_relevante(self) -> None:
        assert es_financiamiento_proyecto("Declaración Jurada de Intereses") is False

    def test_codigo_etica_no_relevante(self) -> None:
        assert es_financiamiento_proyecto("Código de Ética Institucional") is False

    def test_politica_prevencion_no_relevante(self) -> None:
        assert es_financiamiento_proyecto("Política de Prevención de Delitos") is False

    def test_cotizacion_servicio_no_relevante(self) -> None:
        assert es_financiamiento_proyecto("Cotización de Servicio de Mantención") is False

    def test_titulo_neutral_sin_desc_es_relevante_conservador(self) -> None:
        assert es_financiamiento_proyecto("Programa de Apoyo Regional") is True

    def test_titulo_exclusion_con_desc_positiva_descarta_por_titulo(self) -> None:
        assert es_financiamiento_proyecto("Licitación Pública", "Fondo de financiamiento disponible") is False

    def test_descripcion_positiva_sin_exclusion_en_titulo(self) -> None:
        assert es_financiamiento_proyecto("Oportunidad Regional", "Fondo de financiamiento para proyectos") is True

    def test_titulo_vacio_es_relevante_conservador(self) -> None:
        assert es_financiamiento_proyecto("") is True

    def test_licitacion_internacional_excluida(self) -> None:
        assert es_financiamiento_proyecto("Licitación Internacional para Obras") is False

    def test_capital_semilla_es_relevante(self) -> None:
        assert es_financiamiento_proyecto("Capital Semilla para Emprendedores") is True

    def test_programa_fomento_es_relevante(self) -> None:
        assert es_financiamiento_proyecto("Programa de Fomento Productivo") is True

    def test_proyecto_i_mas_d_es_relevante(self) -> None:
        assert es_financiamiento_proyecto("Proyecto de I+D en Biotecnología") is True

    def test_boletin_ingreso_no_relevante(self) -> None:
        assert es_financiamiento_proyecto("Boletín de Ingreso N° 789") is False

    def test_formato_recibo_no_relevante(self) -> None:
        assert es_financiamiento_proyecto("Formato Tipo de Recibo de Pago") is False

    def test_listado_delitos_no_relevante(self) -> None:
        assert es_financiamiento_proyecto("Listado de Delitos Ley 21.000") is False


class TestEsFechaTituloReciente:
    def test_titulo_sin_anio_es_reciente_conservador(self) -> None:
        assert es_fecha_titulo_reciente("Fondo de Innovación") is True

    def test_titulo_con_anio_actual_es_reciente(self) -> None:
        assert es_fecha_titulo_reciente("Convocatoria 2026") is True

    def test_titulo_con_anio_viejo_no_es_reciente(self) -> None:
        assert es_fecha_titulo_reciente("Concurso 2020") is False

    def test_titulo_con_anio_muy_viejo_no_es_reciente(self) -> None:
        assert es_fecha_titulo_reciente("Fondo 2018 Resultados") is False

    def test_ventana_personalizada(self) -> None:
        current_year = datetime.now(UTC).year
        old_year = current_year - 5
        assert es_fecha_titulo_reciente(f"Fondo {old_year}", meses_ventana=60) is True

    def test_anio_futuro_es_reciente(self) -> None:
        assert es_fecha_titulo_reciente("Programa 2027") is True


class TestFiltrarRelevantesRaw:
    def test_filtra_licitaciones(self) -> None:
        items = [
            {"titulo": "Fondo de Innovación 2026", "estado": "ABIERTO"},
            {"titulo": "Licitación Pública N° 42", "estado": "ABIERTO"},
        ]
        result = filtrar_relevantes_raw(items)
        assert len(result) == 1
        assert result[0]["titulo"] == "Fondo de Innovación 2026"

    def test_filtra_por_anio_titulo(self) -> None:
        items = [
            {"titulo": "Concurso 2026", "estado": "ABIERTO"},
            {"titulo": "Concurso 2019 Resultados", "estado": "ABIERTO"},
        ]
        result = filtrar_relevantes_raw(items)
        assert len(result) == 1
        assert result[0]["titulo"] == "Concurso 2026"

    def test_lista_vacia(self) -> None:
        assert filtrar_relevantes_raw([]) == []

    def test_todas_relevantes(self) -> None:
        items = [
            {"titulo": "Fondo CORFO 2026", "estado": "ABIERTO"},
            {"titulo": "Subsidio Sercotec", "estado": "ABIERTO"},
        ]
        result = filtrar_relevantes_raw(items)
        assert len(result) == 2

    def test_todas_irrelevantes(self) -> None:
        items = [
            {"titulo": "Viático Comisión Servicio", "estado": "ABIERTO"},
            {"titulo": "Licitación Pública Hardware", "estado": "ABIERTO"},
        ]
        result = filtrar_relevantes_raw(items)
        assert len(result) == 0

    def test_titulo_none_trata_como_vacio(self) -> None:
        items = [{"titulo": None, "estado": "ABIERTO"}]
        result = filtrar_relevantes_raw(items)
        assert len(result) == 1


class TestFiltrarRelevantes:
    def test_filtra_convocatorias_con_exclusion(self) -> None:
        convocatorias = [
            _conv("Fondo de Innovación 2026"),
            _conv("Licitación Pública N° 100"),
        ]
        result = filtrar_relevantes(convocatorias)
        assert len(result) == 1
        assert result[0].titulo == "Fondo de Innovación 2026"

    def test_filtra_por_anio_viejo(self) -> None:
        convocatorias = [
            _conv("Concurso 2026"),
            _conv("Concurso 2019 Resultados"),
        ]
        result = filtrar_relevantes(convocatorias)
        assert len(result) == 1
        assert result[0].titulo == "Concurso 2026"

    def test_lista_vacia(self) -> None:
        assert filtrar_relevantes([]) == []

    def test_todas_relevantes(self) -> None:
        convocatorias = [
            _conv("Fondo CORFO 2026"),
            _conv("Subsidio Sercotec"),
        ]
        result = filtrar_relevantes(convocatorias)
        assert len(result) == 2
