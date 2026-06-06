"""
Normalización canónica de estados de convocatorias.

Un único lugar para mapear cualquier texto crudo (WordPress, HTML, RSS, LLM)
a los estados canónicos del dominio: ABIERTO, CERRADO, PROXIMAMENTE,
ADJUDICADO, SUSPENDIDO, DESCONOCIDO.

Todos los scrapers y el normalizador DEBEN usar esta función.
Nunca más estados sueltos como 'publish', 'draft', 'ABRIR BARRA DE HERRAMIENTAS'.
"""

import re

_CANONICAL_VIGENTES = frozenset({"ABIERTO", "PROXIMAMENTE"})
_CANONICAL_NO_VIGENTES = frozenset({"CERRADO", "ADJUDICADO", "SUSPENDIDO", "FINALIZADO"})
_CANONICAL_ALL = _CANONICAL_VIGENTES | _CANONICAL_NO_VIGENTES | {"DESCONOCIDO"}

_STATUS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bABIERT[OA]\b", re.IGNORECASE), "ABIERTO"),
    (re.compile(r"\bCERRAD[OA]\b", re.IGNORECASE), "CERRADO"),
    (re.compile(r"\bPRÓ?XIMAMENTE\b", re.IGNORECASE), "PROXIMAMENTE"),
    (re.compile(r"\bPOSTUL[AO]\b", re.IGNORECASE), "ABIERTO"),
    (re.compile(r"\bADJUDICAD[OA]\b", re.IGNORECASE), "ADJUDICADO"),
    (re.compile(r"\bSUSPENDID[OA]\b", re.IGNORECASE), "SUSPENDIDO"),
    (re.compile(r"\bFINALIZAD[OA]\b", re.IGNORECASE), "FINALIZADO"),
    (re.compile(r"\bVIGENTE\b", re.IGNORECASE), "ABIERTO"),
]

# Mapeo explícito de estados de WordPress REST API.
# 'publish' = post publicado = convocatoria activa/vigente.
# 'draft', 'private', 'pending', 'trash' no son estados de apertura útiles.
# NOTA: 'publish' indica que el post está visible, NO necesariamente que la
# convocatoria esté abierta; se usa como proxy en ausencia de campo mejor.
_WP_STATUS_MAP: dict[str, str] = {
    "publish": "ABIERTO",
    "draft": "DESCONOCIDO",
    "private": "DESCONOCIDO",
    "pending": "DESCONOCIDO",
    "trash": "CERRADO",
    "future": "PROXIMAMENTE",
}


def normalize_estado(raw: str | None) -> str:
    """
    Normaliza un texto de estado crudo al estado canónico del dominio.

    Reglas:
    1. Si el texto ya es un estado canónico (uppercase), se devuelve tal cual.
    2. Se evalúan patrones regex en orden de precedencia.
    3. Si nada coincide, devuelve 'DESCONOCIDO'.

    Ejemplos:
        'publish'       -> 'ABIERTO'  (WordPress post status = publicado = vigente)
        'draft'         -> 'DESCONOCIDO'
        'Abierta'       -> 'ABIERTO'
        'Cerrado'       -> 'CERRADO'
        'ABRIR BARRA'   -> 'DESCONOCIDO'  (no coincide con ningún patrón)
        None            -> 'DESCONOCIDO'
    """
    if not raw:
        return "DESCONOCIDO"

    text = raw.strip()

    if not text:
        return "DESCONOCIDO"

    upper = text.upper()

    if upper in _CANONICAL_ALL:
        return upper

    # Mapeo directo de estados WordPress antes de evaluar patrones regex.
    wp_mapped = _WP_STATUS_MAP.get(text.lower())
    if wp_mapped:
        return wp_mapped

    for pattern, canonical in _STATUS_PATTERNS:
        if pattern.search(text):
            return canonical

    return "DESCONOCIDO"
