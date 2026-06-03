"""
Tests unitarios para el motor de detección de cambios (ChangeDetectorService).
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.core.domain.entities import AlertsConfig, Convocatoria, Fuente, RulesConfig, SelectorConfig
from src.core.domain.services import ChangeDetectorService


@pytest.fixture
def mock_fuente_cambios() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="Test Fuente Cambios",
        url_base="https://ejemplo.com",  # type: ignore
        configuracion_reglas=RulesConfig(
            nombre="Test",
            url_busqueda="https://ejemplo.com/fondos",  # type: ignore
            selectores=SelectorConfig(
                contenedor_items="div", identificador="id", titulo="t", descripcion="d", link_detalle="l", estado="e"
            ),
            alertas=AlertsConfig(
                campos_sensibles=["estado", "fecha_cierre", "monto"], ignorar_cambios_en=["descripcion", "titulo"]
            ),
        ),
    )


def test_detect_apertura(mock_fuente_cambios: Fuente) -> None:
    nuevas = [
        Convocatoria(
            fuente_id=mock_fuente_cambios.id,
            identificador_externo="F001",
            titulo="Nueva Convocatoria",
            url_detalle="https://ejemplo.com/f001",  # type: ignore
            estado="ABIERTO",
        )
    ]
    antiguas: dict[str, Convocatoria] = {}

    eventos = ChangeDetectorService.detect_changes(nuevas, antiguas, mock_fuente_cambios)

    assert len(eventos) == 1
    assert eventos[0].tipo == "APERTURA"
    assert eventos[0].es_relevante is True
    assert len(eventos[0].deltas) == 0


def test_detect_modificacion_relevante(mock_fuente_cambios: Fuente) -> None:
    antigua = Convocatoria(
        fuente_id=mock_fuente_cambios.id,
        identificador_externo="F002",
        titulo="Convocatoria Existente",
        url_detalle="https://ejemplo.com/f002",  # type: ignore
        estado="ABIERTO",
        fecha_cierre=datetime(2026, 12, 31, tzinfo=UTC),
    )

    # Cambio en estado (campo sensible)
    nueva = antigua.model_copy(update={"estado": "CERRADO"})

    eventos = ChangeDetectorService.detect_changes([nueva], {"F002": antigua}, mock_fuente_cambios)

    assert len(eventos) == 1
    assert eventos[0].tipo == "MODIFICACION"
    assert eventos[0].es_relevante is True
    assert len(eventos[0].deltas) == 1
    assert eventos[0].deltas[0].campo == "estado"
    assert eventos[0].deltas[0].valor_anterior == "ABIERTO"
    assert eventos[0].deltas[0].valor_nuevo == "CERRADO"


def test_detect_modificacion_no_relevante(mock_fuente_cambios: Fuente) -> None:
    antigua = Convocatoria(
        fuente_id=mock_fuente_cambios.id,
        identificador_externo="F003",
        titulo="Convocatoria Existente",
        url_detalle="https://ejemplo.com/f003",  # type: ignore
        estado="ABIERTO",
    )

    # Cambio en URL detalle (no está en campos sensibles ni ignorados)
    nueva = antigua.model_copy(update={"url_detalle": "https://ejemplo.com/f003-modificado"})

    eventos = ChangeDetectorService.detect_changes([nueva], {"F003": antigua}, mock_fuente_cambios)

    assert len(eventos) == 1
    assert eventos[0].tipo == "MODIFICACION"
    assert eventos[0].es_relevante is False  # No es sensible
    assert len(eventos[0].deltas) == 1
    assert eventos[0].deltas[0].campo == "url_detalle"


def test_ignore_cambios_decorativos(mock_fuente_cambios: Fuente) -> None:
    antigua = Convocatoria(
        fuente_id=mock_fuente_cambios.id,
        identificador_externo="F004",
        titulo="Titulo Original",
        descripcion="Desc original",
        url_detalle="https://ejemplo.com/f004",  # type: ignore
        estado="ABIERTO",
    )

    # Cambio en titulo y descripcion (ambos en ignorar_cambios_en)
    nueva = antigua.model_copy(
        update={"titulo": "Titulo Modificado por CMS", "descripcion": "Desc con typos corregidos"}
    )

    eventos = ChangeDetectorService.detect_changes([nueva], {"F004": antigua}, mock_fuente_cambios)

    assert len(eventos) == 0  # Ningún evento porque todos los cambios fueron ignorados


def test_no_changes(mock_fuente_cambios: Fuente) -> None:
    antigua = Convocatoria(
        fuente_id=mock_fuente_cambios.id,
        identificador_externo="F005",
        titulo="Igual",
        url_detalle="https://ejemplo.com/f005",  # type: ignore
        estado="ABIERTO",
    )
    # Misma info
    nueva = antigua.model_copy()

    eventos = ChangeDetectorService.detect_changes([nueva], {"F005": antigua}, mock_fuente_cambios)

    assert len(eventos) == 0
