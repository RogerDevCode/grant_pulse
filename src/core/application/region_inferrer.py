"""Inferencia determinística de regiones a partir del título y descripción.

Patrones regex específicos de nomenclatura CORFO regional (CDPR).
No usa LLM: solo matching textual determinístico contra regiones canónicas.

Razón: el selector CSS del scraper (h4) no devuelve la región en el HTML
actual de CORFO. Como mitigación, inferimos la región desde el título
cuando este la menciona explícitamente.
"""

from __future__ import annotations

import re

REGIONES_CANONICAS: list[str] = [
    "Arica y Parinacota",
    "Tarapacá",
    "Antofagasta",
    "Atacama",
    "Coquimbo",
    "Valparaíso",
    "Metropolitana",
    "O'Higgins",
    "Maule",
    "Ñuble",
    "Biobío",
    "La Araucanía",
    "Los Ríos",
    "Los Lagos",
    "Aysén",
    "Magallanes",
]


def _normalizar(texto: str) -> str:
    """Minúsculas + sin tildes + sin apostrofes, para matching robusto."""
    texto = texto.lower()
    reemplazos = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "ñ": "n", "'": "", "’": "", "–": " ", "—": " ", "-": " ",
    }
    for origen, destino in reemplazos.items():
        texto = texto.replace(origen, destino)
    return texto


_REGIONES_NORMALIZADAS: dict[str, str] = {
    r: _normalizar(r) for r in REGIONES_CANONICAS
}

_PATRONES: tuple[re.Pattern[str], ...] = (
    # "REGIÓN DE X" — captura hasta delimitador fuerte (greedy, se limpia después)
    re.compile(
        r"region\s+de\s+([a-záéíóúñ\s]+?)(?=\s+region\s|\s+\d|\s+conv\.|\s+cdpr|$)",
        re.IGNORECASE,
    ),
    # "REGIÓN X" sin "de" — greedy, hasta delimitador
    re.compile(
        r"region\s+([a-záéíóúñ\s]+?)(?=\s+region\s|\s+\d{4}|\s+conv\.|\s+cdpr|$)",
        re.IGNORECASE,
    ),
    # "INNOVA REGIÓN X" o "INNOVA REGION X"
    re.compile(r"innova\s+regi[oó]n\s+([a-záéíóúñ]+)", re.IGNORECASE),
    # "SÚMATE A INNOVAR X"
    re.compile(r"s[uú]mate\s+a\s+innovar\s+([a-záéíóúñ\s]+?)(?=\s+\d{4}|$)", re.IGNORECASE),
    # "VIRALIZA ... REGIÓN DE X"
    re.compile(r"viraliza[^.]*?regi[oó]n\s+(?:de\s+)?([a-záéíóúñ\s]+?)$", re.IGNORECASE),
    # "PRIMER CONCURSO INNOVA REGIÓN X 2026"
    re.compile(
        r"primer\s+concurso\s+innova\s+regi[oó]n\s+"
        r"(?:\d{4}\s+)?regi[oó]n\s+(?:de\s+)?([a-záéíóúñ\s]+?)$",
        re.IGNORECASE,
    ),
    # "PRIMER CONCURSO INNOVA REGIÓN CDPR X 2026"
    re.compile(
        r"primer\s+concurso\s+innova\s+regi[oó]n\s+cdpr\s+([a-záéíóúñ\s]+?)\s+\d{4}",
        re.IGNORECASE,
    ),
    # "SEMILLA INICIA AÑO 2026, REGIÓN DE X"
    re.compile(
        r"semilla\s+inicia\s+a[nñ]o\s+\d{4},?\s+regi[oó]n\s+de\s+"
        r"([a-záéíóúñ\s]+?)$",
        re.IGNORECASE,
    ),
    # Variante "INNOVA REGION 2026 REGION DE X"
    re.compile(
        r"innova\s+regi[oó]n\s+\d{4}\s+regi[oó]n\s+(?:de\s+)?"
        r"([a-záéíóúñ\s]+?)$",
        re.IGNORECASE,
    ),
    # "Programa de Difusión Tecnológica – X 2026"
    re.compile(
        r"programa\s+de\s+difusi[oó]n\s+tecnol[oó]gica\s+"
        r"([a-záéíóúñ\s]+?)\s+\d{4}",
        re.IGNORECASE,
    ),
    # "SUMATE INNOVAR – COMITÉ DE DESARROLLO PRODUCTIVO REGIONAL DE X"
    re.compile(
        r"sumate\s+innovar\s+comite\s+de\s+desarrollo\s+productivo\s+regional\s+"
        r"de\s+([a-záéíóúñ\s]+?)$",
        re.IGNORECASE,
    ),
    # "CDPR METROPOLITANO 2026: SÚMATE A INNOVAR X"
    re.compile(
        r"cdpr\s+([a-záéíóúñ\s]+?)(?=\s+\d{4}|\s*:|\s*,|$)",
        re.IGNORECASE,
    ),
)


def _buscar_match(candidato: str) -> str | None:
    """Compara un candidato contra regiones canónicas normalizadas."""
    candidato_norm = _normalizar(candidato.strip().rstrip(",.;:–—-"))
    if not candidato_norm:
        return None
    # Variante sin espacios: "bio bio" → "biobio" para emparejar "biobio"
    candidato_compacto = candidato_norm.replace(" ", "")
    for canonica, normalizada in _REGIONES_NORMALIZADAS.items():
        if candidato_norm == normalizada or candidato_compacto == normalizada:
            return canonica
        if len(normalizada) >= 5:
            if normalizada in candidato_norm:
                return canonica
            canonica_compacta = normalizada.replace(" ", "")
            if canonica_compacta and canonica_compacta in candidato_compacto:
                return canonica
    return None


def inferir_regiones(titulo: str, descripcion: str = "") -> list[str]:
    """Devuelve regiones canónicas detectadas en el texto.

    Args:
        titulo: Título de la convocatoria.
        descripcion: Descripción opcional.

    Returns:
        Lista ordenada y sin duplicados. Vacía si no se detecta ninguna.
    """
    blob = _normalizar(f"{titulo} {descripcion or ''}")
    regiones: set[str] = set()

    for patron in _PATRONES:
        for match in patron.finditer(blob):
            candidato = match.group(1)
            encontrada = _buscar_match(candidato)
            if encontrada:
                regiones.add(encontrada)

    return sorted(regiones)
