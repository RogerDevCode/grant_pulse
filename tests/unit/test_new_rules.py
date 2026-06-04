"""Tests de validación para los archivos de reglas YAML."""

from pathlib import Path

from src.infra.rules_loader import load_rules_from_yaml


def test_load_subdere_rules():
    filepath = Path("rules/subdere.yaml")
    rules = load_rules_from_yaml(filepath)
    assert rules.nombre == "SUBDERE"
    assert rules.estrategia == "subdere_homepage"
    assert rules.selectores is not None
    assert "sala-de-prensa" in rules.selectores.contenedor_items


def test_load_fia_rules():
    filepath = Path("rules/fia.yaml")
    rules = load_rules_from_yaml(filepath)
    assert rules.nombre == "FIA"
    assert rules.estrategia == "json_api"
    assert rules.json_mapping is not None
    assert rules.json_mapping.identificador == "id"
    assert rules.json_mapping.titulo == "title.rendered"


def test_load_corfo_rules():
    filepath = Path("rules/corfo.yaml")
    rules = load_rules_from_yaml(filepath)
    assert rules.nombre == "CORFO"
    assert rules.estrategia == "wp_ajax"
    assert rules.selectores is not None
    assert rules.selectores.contenedor_items == ".caja-resultados_uno"
    assert rules.selectores.link_detalle == ".foot-caja_result a"
    assert rules.selectores.estado == "h6"


def test_load_fosis_rules():
    filepath = Path("rules/fosis.yaml")
    rules = load_rules_from_yaml(filepath)
    assert rules.nombre == "FOSIS"
    assert rules.estrategia == "fosis_multipage"
    assert rules.selectores is not None
    assert rules.selectores.contenedor_items == "div[style*='background-color']"


def test_load_prochile_rules():
    filepath = Path("rules/prochile.yaml")
    rules = load_rules_from_yaml(filepath)
    assert rules.nombre == "PROCHILE"
    assert rules.estrategia == "html_static"
    assert rules.selectores is not None
    assert rules.selectores.contenedor_items == ".tab-pane .shadow-sm"
