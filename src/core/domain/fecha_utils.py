"""
Utilidades de parsing de fechas en formatos chilenos/españoles.

Maneja los formatos más comunes encontrados en sitios gubernamentales chilenos:
- "15 de agosto de 2026"
- "15/08/2026"
- "15-08-2026"
- "2026-08-15"
- "agosto 15, 2026"
"""

import re
from datetime import UTC, datetime

_MESES_ES: dict[str, int] = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}

_PATRON_DIA_MES_ANIO = re.compile(
    r"(\d{1,2})\s+de\s+(\w+)\s+de\s*(\d{4})",
    re.IGNORECASE,
)

_PATRON_SLASH = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")

_PATRON_DASH = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")

_PATRON_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def parse_fecha_chilena(texto: str) -> datetime | None:
    """
    Intenta parsear una fecha en formato chileno a datetime UTC.

    Retorna None si no puede parsear (en lugar de lanzar excepción),
    ya que las fechas en sitios gubernamentales son frecuentemente
    inconsistentes o incompletas.
    """
    if not texto or not texto.strip():
        return None

    texto = texto.strip()

    # "15 de agosto de 2026"
    match = _PATRON_DIA_MES_ANIO.search(texto)
    if match:
        dia_str, mes_nombre, anio_str = match.group(1), match.group(2).lower(), match.group(3)
        mes = _MESES_ES.get(mes_nombre)
        if mes is not None:
            try:
                return datetime(int(anio_str), mes, int(dia_str), tzinfo=UTC)
            except ValueError:
                return None

    # "15/08/2026"
    match = _PATRON_SLASH.match(texto)
    if match:
        dia_str, mes_str, anio_str = match.group(1), match.group(2), match.group(3)
        try:
            return datetime(int(anio_str), int(mes_str), int(dia_str), tzinfo=UTC)
        except ValueError:
            return None

    # "15-08-2026"
    match = _PATRON_DASH.match(texto)
    if match:
        dia_str, mes_str, anio_str = match.group(1), match.group(2), match.group(3)
        try:
            return datetime(int(anio_str), int(mes_str), int(dia_str), tzinfo=UTC)
        except ValueError:
            return None

    # "2026-08-15" (ISO)
    match = _PATRON_ISO.match(texto)
    if match:
        anio_str, mes_str, dia_str = match.group(1), match.group(2), match.group(3)
        try:
            return datetime(int(anio_str), int(mes_str), int(dia_str), tzinfo=UTC)
        except ValueError:
            return None

    return None
