"""Tests para el filtro de vigencia de convocatorias."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import HttpUrl

from src.core.domain.entities import Convocatoria
from src.core.domain.vigencia import es_convocatoria_vigente, filtrar_vigentes, filtrar_vigentes_raw


def _conv(estado: str = "ABIERTO", fecha_cierre: datetime | None = None) -> Convocatoria:
    return Convocatoria(
        fuente_id=uuid4(),
        identificador_externo="test-1",
        titulo="Convocatoria Test",
        url_detalle=HttpUrl("https://example.com/test/"),
        estado=estado,
        fecha_cierre=fecha_cierre,
    )


_NOW = datetime(2026, 6, 2, 12, 0, 0, tzinfo=UTC)
_PASADO = _NOW - timedelta(days=30)
_FUTURO = _NOW + timedelta(days=30)


class TestEsConvocatoriaVigente:
    def test_abierta_es_vigente(self) -> None:
        assert es_convocatoria_vigente(_conv("ABIERTO"), referencia=_NOW) is True

    def test_abierto_es_vigente(self) -> None:
        assert es_convocatoria_vigente(_conv("ABIERTO"), referencia=_NOW) is True

    def test_cerrada_no_vigente(self) -> None:
        assert es_convocatoria_vigente(_conv("CERRADA"), referencia=_NOW) is False

    def test_cerrado_no_vigente(self) -> None:
        assert es_convocatoria_vigente(_conv("CERRADO"), referencia=_NOW) is False

    def test_adjudicada_no_vigente(self) -> None:
        assert es_convocatoria_vigente(_conv("ADJUDICADA"), referencia=_NOW) is False

    def test_suspendida_no_vigente(self) -> None:
        assert es_convocatoria_vigente(_conv("SUSPENDIDA"), referencia=_NOW) is False

    def test_proximamente_es_vigente(self) -> None:
        assert es_convocatoria_vigente(_conv("PROXIMAMENTE"), referencia=_NOW) is True

    def test_sin_estado_con_fecha_futura_es_vigente(self) -> None:
        c = _conv("DESCONOCIDO", fecha_cierre=_FUTURO)
        assert es_convocatoria_vigente(c, referencia=_NOW) is True

    def test_sin_estado_con_fecha_pasada_no_vigente(self) -> None:
        c = _conv("DESCONOCIDO", fecha_cierre=_PASADO)
        assert es_convocatoria_vigente(c, referencia=_NOW) is False

    def test_sin_estado_sin_fecha_es_vigente_conservador(self) -> None:
        c = _conv("DESCONOCIDO", fecha_cierre=None)
        assert es_convocatoria_vigente(c, referencia=_NOW) is True

    def test_abierta_con_fecha_pasada_sigue_vigente(self) -> None:
        c = _conv("ABIERTO", fecha_cierre=_PASADO)
        assert es_convocatoria_vigente(c, referencia=_NOW) is True

    def test_vacio_es_desconocido_vigente(self) -> None:
        c = _conv("", fecha_cierre=None)
        assert es_convocatoria_vigente(c, referencia=_NOW) is True


class TestFiltrarVigentes:
    def test_filtra_cerradas(self) -> None:
        convocatorias = [_conv("ABIERTO"), _conv("CERRADA"), _conv("ABIERTO")]
        result = filtrar_vigentes(convocatorias, referencia=_NOW)
        assert len(result) == 2
        assert all(c.estado != "CERRADA" for c in result)

    def test_filtra_por_fecha(self) -> None:
        convocatorias = [
            _conv("DESCONOCIDO", fecha_cierre=_FUTURO),
            _conv("DESCONOCIDO", fecha_cierre=_PASADO),
        ]
        result = filtrar_vigentes(convocatorias, referencia=_NOW)
        assert len(result) == 1
        assert result[0].fecha_cierre == _FUTURO

    def test_lista_vacia(self) -> None:
        assert filtrar_vigentes([], referencia=_NOW) == []

    def test_todas_vigentes(self) -> None:
        convocatorias = [_conv("ABIERTO"), _conv("PROXIMAMENTE")]
        result = filtrar_vigentes(convocatorias, referencia=_NOW)
        assert len(result) == 2


class TestFiltrarVigentesRaw:
    def test_filtra_cerradas_raw(self) -> None:
        items = [
            {"titulo": "A", "estado": "ABIERTO", "fecha_cierre": None},
            {"titulo": "B", "estado": "CERRADO", "fecha_cierre": None},
            {"titulo": "C", "estado": "ABIERTA", "fecha_cierre": None},
        ]
        result = filtrar_vigentes_raw(items, referencia=_NOW)
        assert len(result) == 2

    def test_filtra_por_fecha_raw(self) -> None:
        items = [
            {"titulo": "A", "estado": "DESCONOCIDO", "fecha_cierre": "15/08/2026"},
            {"titulo": "B", "estado": "DESCONOCIDO", "fecha_cierre": "01/01/2020"},
        ]
        result = filtrar_vigentes_raw(items, referencia=_NOW)
        assert len(result) == 1
        assert result[0]["titulo"] == "A"

    def test_sin_fecha_ni_estado_pasa(self) -> None:
        items = [{"titulo": "X", "estado": None, "fecha_cierre": None}]
        result = filtrar_vigentes_raw(items, referencia=_NOW)
        assert len(result) == 1

    def test_fecha_formato_chileno(self) -> None:
        items = [
            {"titulo": "Vigente", "estado": "DESCONOCIDO", "fecha_cierre": "15 de agosto de 2026"},
            {"titulo": "Vencida", "estado": "DESCONOCIDO", "fecha_cierre": "15 de enero de 2020"},
        ]
        result = filtrar_vigentes_raw(items, referencia=_NOW)
        assert len(result) == 1
        assert result[0]["titulo"] == "Vigente"
