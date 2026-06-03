"""
Tests unitarios para el cargador y validador de archivos de reglas YAML.
"""

from pathlib import Path

import pytest

from src.core.domain.exceptions import ConfigurationError
from src.infra.rules_loader import load_rules_from_yaml


def test_load_valid_corfo_rules() -> None:
    """Verifica que el YAML de CORFO se cargue y valide sin errores."""
    filepath = Path(__file__).parents[2] / "rules" / "corfo.yaml"
    rules = load_rules_from_yaml(filepath)

    assert rules.nombre == "CORFO"
    assert rules.estrategia == "wp_ajax"
    assert rules.selectores is not None
    assert rules.selectores.contenedor_items == ".caja-resultados_uno"
    assert rules.selectores.titulo == "h4"
    assert "fecha_cierre" in rules.alertas.campos_sensibles


def test_load_valid_sercotec_rules() -> None:
    """Verifica que el YAML de Sercotec se cargue y valide sin errores."""
    filepath = Path(__file__).parents[2] / "rules" / "sercotec.yaml"
    rules = load_rules_from_yaml(filepath)

    assert rules.nombre == "SERCOTEC"
    assert rules.selectores is not None
    assert rules.selectores.identificador == "h3.card-title"
    assert "estado" in rules.alertas.campos_sensibles


def test_load_nonexistent_file() -> None:
    """Verifica que cargar un archivo inexistente lance ConfigurationError."""
    filepath = Path(__file__).parents[2] / "rules" / "inexistente.yaml"
    with pytest.raises(ConfigurationError) as exc_info:
        load_rules_from_yaml(filepath)
    assert "El archivo de reglas no existe" in str(exc_info.value)


def test_load_invalid_yaml_syntax(tmp_path: Path) -> None:
    """Verifica que sintaxis incorrecta de YAML lance ConfigurationError."""
    bad_yaml = tmp_path / "bad_syntax.yaml"
    bad_yaml.write_text("nombre: : : duplicado", encoding="utf-8")

    with pytest.raises(ConfigurationError) as exc_info:
        load_rules_from_yaml(bad_yaml)
    assert "Error de sintaxis YAML" in str(exc_info.value)


def test_load_invalid_schema(tmp_path: Path) -> None:
    """Verifica que un YAML con estructura inválida lance ConfigurationError."""
    bad_schema = tmp_path / "bad_schema.yaml"
    bad_schema.write_text(
        """
nombre: "Inválido"
url_busqueda: "no-es-una-url"
selectores:
  contenedor_items: "div"
        """,
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError) as exc_info:
        load_rules_from_yaml(bad_schema)
    assert "Esquema de reglas inválido" in str(exc_info.value)
