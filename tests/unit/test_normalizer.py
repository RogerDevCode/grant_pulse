"""
Tests unitarios para el normalizador de datos.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.core.application.normalizer import DataNormalizer
from src.core.domain.entities import Fuente, NormalizerConfig, NormalizerItem, RulesConfig, SelectorConfig


@pytest.fixture
def mock_fuente_normalizador() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="Test Fuente Normalizador",
        url_base="https://ejemplo.com",  # type: ignore
        configuracion_reglas=RulesConfig(
            nombre="Test",
            url_busqueda="https://ejemplo.com/fondos",  # type: ignore
            selectores=SelectorConfig(
                contenedor_items="div", identificador="id", titulo="t", descripcion="d", link_detalle="l", estado="e"
            ),
            normalizadores=NormalizerConfig(
                fecha_cierre=NormalizerItem(
                    regex_extraction=r"Cierre:\s*(\d{2}/\d{2}/\d{4})", formato_salida="%d/%m/%Y"
                ),
                monto=NormalizerItem(
                    regex_extraction=r"Monto máximo:\s*\$?([\d\.]+)",
                ),
            ),
        ),
    )


def test_normalize_and_map_success(mock_fuente_normalizador: Fuente) -> None:
    raw_items: list[dict[str, str | None]] = [
        {
            "identificador": "F001",
            "titulo": "Fondo Semilla",
            "descripcion": "Descripción del fondo",
            "url_detalle": "/fondos/F001",
            "estado": "ABIERTO",
            "fecha_cierre": "Cierre: 31/12/2026",
            "monto": "Monto máximo: $15.000.000",
        }
    ]

    convocatorias = DataNormalizer.normalize_and_map(raw_items, mock_fuente_normalizador)

    assert len(convocatorias) == 1
    c = convocatorias[0]
    assert c.identificador_externo == "F001"
    assert c.titulo == "Fondo Semilla"
    assert c.descripcion == "Descripción del fondo"
    assert str(c.url_detalle) == "https://ejemplo.com/fondos/F001"
    assert c.estado == "ABIERTO"

    assert c.fecha_cierre == datetime(2026, 12, 31, tzinfo=UTC)
    assert c.monto == 15000000.0


def test_normalize_and_map_missing_url_detalle_skips_gracefully(mock_fuente_normalizador: Fuente) -> None:
    raw_items: list[dict[str, str | None]] = [
        {
            "identificador": "F002",
            "titulo": "Fondo Sin Enlace",
            "estado": "ABIERTO",
        }
    ]

    convocatorias = DataNormalizer.normalize_and_map(raw_items, mock_fuente_normalizador)
    assert len(convocatorias) == 0


def test_normalize_and_map_missing_estado_defaults_to_desconocido(mock_fuente_normalizador: Fuente) -> None:
    raw_items: list[dict[str, str | None]] = [
        {
            "identificador": "F002B",
            "titulo": "Fondo Sin Estado",
            "url_detalle": "/fondos/F002B",
        }
    ]

    convocatorias = DataNormalizer.normalize_and_map(raw_items, mock_fuente_normalizador)
    assert len(convocatorias) == 1
    assert convocatorias[0].estado == "DESCONOCIDO"


def test_normalize_and_map_regex_failure_skips_gracefully(mock_fuente_normalizador: Fuente) -> None:
    raw_items: list[dict[str, str | None]] = [
        {
            "identificador": "F003",
            "titulo": "Fondo Error Regex",
            "url_detalle": "/fondos/F003",
            "estado": "ABIERTO",
            "fecha_cierre": "Termina el 31-12-2026",
        }
    ]

    convocatorias = DataNormalizer.normalize_and_map(raw_items, mock_fuente_normalizador)
    assert len(convocatorias) == 0


def test_normalize_and_map_date_parse_failure_skips_gracefully(mock_fuente_normalizador: Fuente) -> None:
    raw_items: list[dict[str, str | None]] = [
        {
            "identificador": "F004",
            "titulo": "Fondo Error Parse",
            "url_detalle": "/fondos/F004",
            "estado": "ABIERTO",
            "fecha_cierre": "Cierre: 99/99/9999",
        }
    ]

    convocatorias = DataNormalizer.normalize_and_map(raw_items, mock_fuente_normalizador)
    assert len(convocatorias) == 0


def test_normalize_and_map_float_parse_failure_skips_gracefully(mock_fuente_normalizador: Fuente) -> None:
    raw_items: list[dict[str, str | None]] = [
        {
            "identificador": "F005",
            "titulo": "Fondo Error Monto",
            "url_detalle": "/fondos/F005",
            "estado": "ABIERTO",
            "monto": "Monto máximo: Muchos millones",
        }
    ]
    assert mock_fuente_normalizador.configuracion_reglas.normalizadores.monto is not None
    mock_fuente_normalizador.configuracion_reglas.normalizadores.monto.regex_extraction = r"Monto máximo:\s*(.*)"

    convocatorias = DataNormalizer.normalize_and_map(raw_items, mock_fuente_normalizador)
    assert len(convocatorias) == 0


def test_normalize_and_map_mixed_items_healthy_survive(mock_fuente_normalizador: Fuente) -> None:
    raw_items: list[dict[str, str | None]] = [
        {
            "identificador": "GOOD1",
            "titulo": "Fondo Bueno",
            "url_detalle": "/fondos/GOOD1",
            "estado": "ABIERTO",
            "fecha_cierre": "Cierre: 31/12/2026",
        },
        {
            "identificador": "BAD1",
            "titulo": "Fondo Sin URL",
            "estado": "ABIERTO",
        },
        {
            "identificador": "GOOD2",
            "titulo": "Otro Fondo Bueno",
            "url_detalle": "/fondos/GOOD2",
            "estado": "PROXIMAMENTE",
        },
    ]

    convocatorias = DataNormalizer.normalize_and_map(raw_items, mock_fuente_normalizador)
    assert len(convocatorias) == 2
    assert convocatorias[0].identificador_externo == "GOOD1"
    assert convocatorias[1].identificador_externo == "GOOD2"
