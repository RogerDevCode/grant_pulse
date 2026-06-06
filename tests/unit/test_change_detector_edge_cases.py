"""
Tests de regresión para detección de cambios — edge cases no cubiertos.

Cubre: campos_sensibles vacío, ignorar_cambios_en que solapa con
campos_sensibles, deltas mixtos (algunos sensibles + algunos ignorados),
y múltiples convocatorias con combinaciones variadas.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.core.domain.entities import AlertsConfig, Convocatoria, Fuente, RulesConfig, SelectorConfig
from src.core.domain.services import ChangeDetectorService


@pytest.fixture
def fuente_sin_sensibles() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="Sin Sensibles",
        url_base="https://ejemplo.com",  # type: ignore
        configuracion_reglas=RulesConfig(
            nombre="Sin Sensibles",
            url_busqueda="https://ejemplo.com/fondos",  # type: ignore
            selectores=SelectorConfig(contenedor_items="div", identificador="id", titulo="t", descripcion="d", link_detalle="l", estado="e"),
            alertas=AlertsConfig(campos_sensibles=[], ignorar_cambios_en=[]),
        ),
    )


@pytest.fixture
def fuente_solapados() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="Solapados",
        url_base="https://ejemplo.com",  # type: ignore
        configuracion_reglas=RulesConfig(
            nombre="Solapados",
            url_busqueda="https://ejemplo.com/fondos",  # type: ignore
            selectores=SelectorConfig(contenedor_items="div", identificador="id", titulo="t", descripcion="d", link_detalle="l", estado="e"),
            alertas=AlertsConfig(campos_sensibles=["estado", "descripcion"], ignorar_cambios_en=["descripcion"]),
        ),
    )


def test_empty_campos_sensibles_all_non_relevant(fuente_sin_sensibles: Fuente) -> None:
    antigua = Convocatoria(
        fuente_id=fuente_sin_sensibles.id,
        identificador_externo="X001",
        titulo="Original",
        url_detalle="https://ejemplo.com/x001",  # type: ignore
        estado="ABIERTO",
    )
    nueva = antigua.model_copy(update={"estado": "CERRADO", "titulo": "Modificado"})

    eventos = ChangeDetectorService.detect_changes([nueva], {"X001": antigua}, fuente_sin_sensibles)

    assert len(eventos) == 1
    assert eventos[0].tipo == "MODIFICACION"
    assert eventos[0].es_relevante is False


def test_ignored_field_takes_precedence_over_sensible(fuente_solapados: Fuente) -> None:
    antigua = Convocatoria(
        fuente_id=fuente_solapados.id,
        identificador_externo="Y001",
        titulo="Original",
        descripcion="Desc original",
        url_detalle="https://ejemplo.com/y001",  # type: ignore
        estado="ABIERTO",
    )
    nueva = antigua.model_copy(update={"descripcion": "Desc nueva"})

    eventos = ChangeDetectorService.detect_changes([nueva], {"Y001": antigua}, fuente_solapados)

    assert len(eventos) == 0


def test_mixed_deltas_sensitive_and_ignored(fuente_solapados: Fuente) -> None:
    antigua = Convocatoria(
        fuente_id=fuente_solapados.id,
        identificador_externo="Z001",
        titulo="Original",
        descripcion="Desc original",
        url_detalle="https://ejemplo.com/z001",  # type: ignore
        estado="ABIERTO",
    )
    nueva = antigua.model_copy(update={"estado": "CERRADO", "descripcion": "Desc nueva"})

    eventos = ChangeDetectorService.detect_changes([nueva], {"Z001": antigua}, fuente_solapados)

    assert len(eventos) == 1
    assert eventos[0].es_relevante is True
    delta_campos = {d.campo for d in eventos[0].deltas}
    assert "estado" in delta_campos
    assert "descripcion" not in delta_campos


def test_multiple_convocatorias_mixed_events() -> None:
    fuente = Fuente(
        id=uuid4(),
        nombre="Mix",
        url_base="https://ejemplo.com",  # type: ignore
        configuracion_reglas=RulesConfig(
            nombre="Mix",
            url_busqueda="https://ejemplo.com/fondos",  # type: ignore
            selectores=SelectorConfig(contenedor_items="div", identificador="id", titulo="t", descripcion="d", link_detalle="l", estado="e"),
            alertas=AlertsConfig(campos_sensibles=["estado"], ignorar_cambios_en=["descripcion"]),
        ),
    )

    antigua_1 = Convocatoria(
        fuente_id=fuente.id,
        identificador_externo="M1",
        titulo="Existente A",
        url_detalle="https://ejemplo.com/m1",  # type: ignore
        estado="ABIERTO",
    )
    antigua_2 = Convocatoria(
        fuente_id=fuente.id,
        identificador_externo="M2",
        titulo="Existente B",
        url_detalle="https://ejemplo.com/m2",  # type: ignore
        estado="ABIERTO",
    )

    nueva_1 = antigua_1.model_copy(update={"estado": "CERRADO"})
    nueva_2 = antigua_2.model_copy(update={"descripcion": "Solo cosmético"})
    nueva_3 = Convocatoria(
        fuente_id=fuente.id,
        identificador_externo="M3",
        titulo="Nueva C",
        url_detalle="https://ejemplo.com/m3",  # type: ignore
        estado="ABIERTO",
    )

    antiguas = {"M1": antigua_1, "M2": antigua_2}
    nuevas = [nueva_1, nueva_2, nueva_3]

    eventos = ChangeDetectorService.detect_changes(nuevas, antiguas, fuente)

    assert len(eventos) == 2
    tipos = {(e.tipo, e.es_relevante) for e in eventos}
    assert ("APERTURA", True) in tipos
    assert ("MODIFICACION", True) in tipos


def test_fecha_cierre_change_is_detected() -> None:
    fuente = Fuente(
        id=uuid4(),
        nombre="Fecha",
        url_base="https://ejemplo.com",  # type: ignore
        configuracion_reglas=RulesConfig(
            nombre="Fecha",
            url_busqueda="https://ejemplo.com/fondos",  # type: ignore
            selectores=SelectorConfig(contenedor_items="div", identificador="id", titulo="t", descripcion="d", link_detalle="l", estado="e"),
            alertas=AlertsConfig(campos_sensibles=["fecha_cierre"], ignorar_cambios_en=[]),
        ),
    )

    antigua = Convocatoria(
        fuente_id=fuente.id,
        identificador_externo="F001",
        titulo="Fondo",
        url_detalle="https://ejemplo.com/f001",  # type: ignore
        estado="ABIERTO",
        fecha_cierre=datetime(2026, 6, 30, tzinfo=UTC),
    )
    nueva = antigua.model_copy(update={"fecha_cierre": datetime(2026, 12, 31, tzinfo=UTC)})

    eventos = ChangeDetectorService.detect_changes([nueva], {"F001": antigua}, fuente)

    assert len(eventos) == 1
    assert eventos[0].es_relevante is True
    assert eventos[0].deltas[0].campo == "fecha_cierre"


def test_monto_change_is_detected() -> None:
    fuente = Fuente(
        id=uuid4(),
        nombre="Monto",
        url_base="https://ejemplo.com",  # type: ignore
        configuracion_reglas=RulesConfig(
            nombre="Monto",
            url_busqueda="https://ejemplo.com/fondos",  # type: ignore
            selectores=SelectorConfig(contenedor_items="div", identificador="id", titulo="t", descripcion="d", link_detalle="l", estado="e"),
            alertas=AlertsConfig(campos_sensibles=["monto"], ignorar_cambios_en=[]),
        ),
    )

    antigua = Convocatoria(
        fuente_id=fuente.id,
        identificador_externo="Q001",
        titulo="Fondo",
        url_detalle="https://ejemplo.com/q001",  # type: ignore
        estado="ABIERTO",
        monto=10000000.0,
    )
    nueva = antigua.model_copy(update={"monto": 20000000.0})

    eventos = ChangeDetectorService.detect_changes([nueva], {"Q001": antigua}, fuente)

    assert len(eventos) == 1
    assert eventos[0].es_relevante is True
    assert eventos[0].deltas[0].campo == "monto"
