"""Tests para inferencia determinística de regiones desde título/descripción."""

import pytest

from src.core.application.region_inferrer import (
    REGIONES_CANONICAS,
    inferir_regiones,
)


@pytest.mark.parametrize(
    "titulo,descripcion,esperado",
    [
        # ─── Casos positivos: regiones detectadas ────────────────────────
        (
            "DESARROLLA INVERSIÓN PRODUCTIVA – REGIÓN DE ÑUBLE – 1° CONVOCATORIA 2026",
            "",
            ["Ñuble"],
        ),
        (
            "INNOVA REGIÓN – REGIÓN DE TARAPACÁ 2026",
            "",
            ["Tarapacá"],
        ),
        (
            "Súmate a Innovar Los Lagos 2026",
            "",
            ["Los Lagos"],
        ),
        (
            "Viraliza Eventos Región de Valparaíso",
            "",
            ["Valparaíso"],
        ),
        (
            "PRIMER CONCURSO INNOVA REGION 2026 REGION DE ARICA Y PARINACOTA",
            "",
            ["Arica y Parinacota"],
        ),
        (
            "DESARROLLA INVERSIÓN PRODUCTIVA – REGIÓN DE AYSÉN – 2° CONVOCATORIA 2026 CDPR",
            "",
            ["Aysén"],
        ),
        (
            "RED PROVEEDORES – REGIÓN DE LA ARAUCANÍA – 1° CONVOCATORIA 2026 ETAPA DESARROLLO",
            "",
            ["La Araucanía"],
        ),
        (
            "PRIMERA CONVOCATORIA SEMILLA INICIA AÑO 2026, REGIÓN DE LA ARAUCANÍA",
            "",
            ["La Araucanía"],
        ),
        (
            "DESARROLLA INVERSIÓN PRODUCTIVA – REGIÓN DE COQUIMBO – 1° CONVOCATORIA 2026",
            "",
            ["Coquimbo"],
        ),
        (
            "RED PROVEEDORES – REGIÓN METROPOLITANA – ETAPA DESARROLLO 2026 CDPR",
            "",
            ["Metropolitana"],
        ),
        (
            "INNOVA REGIÓN – REGIÓN DE TARAPACÁ 2026",
            "Línea de apoyo a la innovación productiva regional",
            ["Tarapacá"],
        ),
        (
            "Garantía COBEX",
            "Mecanismo de apoyo para empresas relacionadas con el comercio exterior",
            [],
        ),
        (
            "Crédito Verde",
            "Programa de financiamiento para mitigar cambio climático",
            [],
        ),
        (
            "",
            "",
            [],
        ),
    ],
)
def test_inferir_regiones_casos_representativos(titulo, descripcion, esperado):
    assert inferir_regiones(titulo, descripcion) == esperado


def test_inferir_regiones_sin_duplicados():
    """Si múltiples patrones matchean la misma región, solo aparece una vez."""
    titulo = "INNOVA REGIÓN – REGIÓN DE MAULE 2026"
    regiones = inferir_regiones(titulo, "")
    assert regiones == ["Maule"]


def test_inferir_regiones_orden_deterministico():
    """El orden de salida es alfabético, independiente del orden de matching."""
    titulo = "REGIÓN DE TARAPACÁ – REGIÓN DE ARICA Y PARINACOTA – REGIÓN DE ANTOFAGASTA"
    regiones = inferir_regiones(titulo, "")
    assert regiones == ["Antofagasta", "Arica y Parinacota", "Tarapacá"]


def test_inferir_regiones_tolerante_a_mayusculas_y_tildes():
    """Mayúsculas, minúsculas, tildes y sin tildes deben matchear igual."""
    casos = [
        ("región de ñuble – convocatoria", ["Ñuble"]),
        ("REGION DE NUBLE – CONVOCATORIA", ["Ñuble"]),
        ("Región del Maule", ["Maule"]),
        ("Region de Bio Bio", ["Biobío"]),
        ("REGION DE BIOBÍO 2026", ["Biobío"]),
    ]
    for titulo, esperado in casos:
        assert inferir_regiones(titulo, "") == esperado, f"Falla con: {titulo!r}"


def test_lista_regiones_canonicas_exhaustiva():
    """Las 16 regiones canónicas están presentes en la lista."""
    assert len(REGIONES_CANONICAS) == 16
    assert "Arica y Parinacota" in REGIONES_CANONICAS
    assert "Biobío" in REGIONES_CANONICAS
    assert "Magallanes" in REGIONES_CANONICAS


def test_no_falsos_positivos_palabras_cortas():
    """Palabras como 'bioagropecuario', 'micro' no deben asignar región."""
    casos_negativos = [
        "Red Tecnológica GTT+ silvoagropecuario",
        "Fondo Etapas Tempranas micro pequeñas empresas",
        "Garantía COBEX comercio exterior",
        "Crédito Verde sustentabilidad",
    ]
    for titulo in casos_negativos:
        regiones = inferir_regiones(titulo, "")
        # No debe matchear Biobío por substrings espurios
        assert "Biobío" not in regiones, f"Falso positivo con: {titulo!r}"
