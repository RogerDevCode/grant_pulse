"""
Tests de regresión para carga de reglas YAML — edge cases no cubiertos.
"""

from pathlib import Path

import pytest

from src.core.domain.exceptions import ConfigurationError
from src.infra.rules_loader import load_rules_from_yaml


def test_load_empty_yaml_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="no contiene un diccionario válido"):
        load_rules_from_yaml(empty)


def test_load_yaml_with_list_root(tmp_path: Path) -> None:
    list_root = tmp_path / "list_root.yaml"
    list_root.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="no contiene un diccionario válido"):
        load_rules_from_yaml(list_root)


def test_load_yaml_with_none_root(tmp_path: Path) -> None:
    none_root = tmp_path / "none_root.yaml"
    none_root.write_text("null\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="no contiene un diccionario válido"):
        load_rules_from_yaml(none_root)


def test_load_yaml_missing_required_field_nombre(tmp_path: Path) -> None:
    missing_nombre = tmp_path / "no_nombre.yaml"
    missing_nombre.write_text(
        """
url_busqueda: "https://ejemplo.com"
selectores:
  contenedor_items: "div"
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="Esquema de reglas inválido"):
        load_rules_from_yaml(missing_nombre)


def test_load_yaml_missing_required_field_url_busqueda(tmp_path: Path) -> None:
    missing_url = tmp_path / "no_url.yaml"
    missing_url.write_text(
        """
nombre: "Test"
selectores:
  contenedor_items: "div"
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="Esquema de reglas inválido"):
        load_rules_from_yaml(missing_url)


def test_load_yaml_missing_required_field_contenedor(tmp_path: Path) -> None:
    missing_container = tmp_path / "no_container.yaml"
    missing_container.write_text(
        """
nombre: "Test"
url_busqueda: "https://ejemplo.com"
selectores:
  titulo: "h2"
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="Esquema de reglas inválido"):
        load_rules_from_yaml(missing_container)


def test_load_valid_minimal_yaml(tmp_path: Path) -> None:
    minimal = tmp_path / "minimal.yaml"
    minimal.write_text(
        """
nombre: "Minimal"
url_busqueda: "https://ejemplo.com"
selectores:
  contenedor_items: "div"
  identificador: "attr:data-id"
  titulo: "h2"
""",
        encoding="utf-8",
    )
    rules = load_rules_from_yaml(minimal)
    assert rules.nombre == "Minimal"
    assert rules.estrategia == "html_static"
    assert rules.alertas.campos_sensibles == []
    assert rules.alertas.ignorar_cambios_en == []
