"""Tests para el estado PERMANENTE de convocatorias."""
from datetime import UTC, datetime

import pytest

from src.core.application.normalizer import DataNormalizer
from src.core.domain.entities import Fuente, RulesConfig
from src.core.domain.estado_normalizer import normalize_estado


@pytest.fixture
def fuente_test():
    """Fuente de prueba con configuración mínima."""
    config = RulesConfig(
        nombre="Test Source",
        url_busqueda="https://example.com/buscar",
        regiones_defecto=["Nacional"],
    )
    return Fuente(
        id=1,
        nombre="Test Source",
        url_base="https://example.com",
        configuracion_reglas=config,
        activa=True,
    )


def test_normalize_estado_permanente():
    """Verifica que PERMANENTE se normaliza correctamente."""
    assert normalize_estado("PERMANENTE") == "PERMANENTE"
    assert normalize_estado("permanente") == "PERMANENTE"
    assert normalize_estado("Permanente") == "PERMANENTE"


def test_normalize_estado_permanente_en_frases():
    """Verifica que PERMANENTE se detecta en frases comunes."""
    assert normalize_estado("abierto permanente") == "PERMANENTE"
    assert normalize_estado("convocatoria permanente") == "PERMANENTE"
    assert normalize_estado("fondo permanente") == "PERMANENTE"


def test_normalizer_promueve_a_permanente_sin_fecha(fuente_test):
    """Verifica que convocatorias sin fecha de cierre se promueven a PERMANENTE."""
    raw_items = [
        {
            "identificador": "test-1",
            "titulo": "Convocatoria sin fecha",
            "estado": "DESCONOCIDO",
            "fecha_cierre": None,
            "url_detalle": "https://example.com/1",
        }
    ]

    result = DataNormalizer.normalize_and_map(raw_items, fuente_test)

    assert len(result) == 1
    assert result[0].estado == "PERMANENTE"
    assert result[0].fecha_cierre is None


def test_normalizer_promueve_a_abierto_con_fecha_futura(fuente_test):
    """Verifica que convocatorias con fecha futura se promueven a ABIERTO."""
    fecha_futura = datetime(2026, 12, 31, tzinfo=UTC).isoformat()
    raw_items = [
        {
            "identificador": "test-2",
            "titulo": "Convocatoria con fecha",
            "estado": "DESCONOCIDO",
            "fecha_cierre": fecha_futura,
            "url_detalle": "https://example.com/2",
        }
    ]

    result = DataNormalizer.normalize_and_map(raw_items, fuente_test)

    assert len(result) == 1
    assert result[0].estado == "ABIERTO"
    assert result[0].fecha_cierre is not None


def test_normalizer_descarta_con_fecha_pasada(fuente_test):
    """Verifica que convocatorias con fecha pasada se descartan."""
    fecha_pasada = datetime(2020, 1, 1, tzinfo=UTC).isoformat()
    raw_items = [
        {
            "identificador": "test-3",
            "titulo": "Convocatoria vencida",
            "estado": "DESCONOCIDO",
            "fecha_cierre": fecha_pasada,
            "url_detalle": "https://example.com/3",
        }
    ]

    result = DataNormalizer.normalize_and_map(raw_items, fuente_test)

    # Las convocatorias con fecha pasada se mantienen pero se fuerzan a estado CERRADO
    assert len(result) == 1
    assert result[0].estado == "CERRADO"


def test_normalizer_preserva_estado_abierto_sin_fecha(fuente_test):
    """Verifica que convocatorias ya marcadas como ABIERTO se preservan."""
    raw_items = [
        {
            "identificador": "test-4",
            "titulo": "Convocatoria ya abierta",
            "estado": "ABIERTO",
            "fecha_cierre": None,
            "url_detalle": "https://example.com/4",
        }
    ]

    result = DataNormalizer.normalize_and_map(raw_items, fuente_test)

    assert len(result) == 1
    assert result[0].estado == "ABIERTO"  # No se cambia a PERMANENTE
