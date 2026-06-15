"""Tests para la inferencia de región con LLM."""

from unittest.mock import patch
from uuid import uuid4

from src.core.application.normalizer import DataNormalizer
from src.core.domain.entities import Fuente, RulesConfig, SelectorConfig


def _make_source() -> Fuente:
    return Fuente(
        id=uuid4(),
        nombre="Fuente Región",
        url_base="https://ejemplo.cl",
        configuracion_reglas=RulesConfig(
            nombre="Fuente Región",
            url_busqueda="https://ejemplo.cl/fondos",
            selectores=SelectorConfig(
                contenedor_items="div",
                identificador="id",
                titulo="h2",
                descripcion="p",
                link_detalle="a",
                estado="span",
            ),
        ),
    )


def test_normalize_and_map_infers_region_when_missing() -> None:
    fuente = _make_source()

    with patch("src.core.application.normalizer._infer_region_with_llm", return_value="Metropolitana") as infer_mock:
        convocatorias = DataNormalizer.normalize_and_map(
            [
                {
                    "identificador": "F-1",
                    "titulo": "Fondo para emprendedores de la Región Metropolitana",
                    "descripcion": "Apoyo a startups ubicadas en Santiago.",
                    "url_detalle": "/fondos/F-1",
                    "estado": "ABIERTO",
                }
            ],
            fuente,
        )

    assert len(convocatorias) == 1
    assert convocatorias[0].region == "Metropolitana"
    infer_mock.assert_called_once()
