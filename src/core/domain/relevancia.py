"""Servicio de dominio: filtro de relevancia de convocatorias.

Filtra items que NO representan financiamiento a proyectos:
- Licitaciones, compras públicas, cotizaciones
- Documentos administrativos (resoluciones de adjudicación, actas, declaraciones juradas)
- Contrataciones de consultoría/auditoría interna
- Normativas, códigos, políticas institucionales
- Eventos/campañas sin fondo concursable
- Certificaciones/sellos sin componente financiero directo

Funciona sobre dicts crudos (pre-hidratación) y sobre entidades Convocatoria.
Se aplica como post-procesamiento después de la extracción, antes de vigencia.
"""

import re
from typing import Any

from src.infra.logging import get_logger

logger = get_logger(__name__)

_EXCLUSION_PATTERNS = re.compile(
    r"\b("
    r"licitaci[óo]n\s+(p[úu]blica|abierta|cerrada|internacional|nacional)?"
    r"|compra\s+(de\s+)?(maquinaria|equipo|servidor|storage|disco|hardware|software|veh[ií]culo|mobiliario|insumo)"
    r"|solicitud\s+de\s+cotizaci[óo]n"
    r"|cotizaci[óo]n\s+(de\s+)?(servicio|obra|suministro)"
    r"|resoluci[óo]n\s+(exenta|modificatoria)?\s*(n[°oº])?\s*\d+.*(adjudica|rechaza|modifica)"
    r"|acta\s+de\s+(postulaci[óo]n|admisibilidad|recepci[óo]n|apertura)"
    r"|declaraci[óo]n\s+jurada"
    r"|c[óo]digo\s+de\s+[ée]tica"
    r"|pol[ií]tica\s+de\s+(prevenci[óo]n|delito|seguridad|privacidad)"
    r"|formato\s+(tipo\s+)?(de\s+)?(recibo|documento|certificado)"
    r"|vi[aá]tico"
    r"|bolet[ií]n\s+de\s+ingreso"
    r"|contrataci[óo]n\s+(de\s+)?(servicio|consultor[ií]a|asesor[ií]a|auditor[ií]a)"
    r"|procedimiento\s+y\s+mecanismo\s+para\s+la\s+compra"
    r"|listado\s+de\s+delitos"
    r"|modelo\s+referencial\s+de\s+ordenanza"
    r")\b",
    re.IGNORECASE,
)

_YEAR_IN_TITLE = re.compile(
    r"\b(20[0-2]\d)\b",
)

_FUNDING_POSITIVE_PATTERNS = re.compile(
    r"\b("
    r"fondo|fondos|financiamiento|cofinanciamiento|subsidio|subvenci[óo]n|"
    r"capital\s+semilla|semilla\s+(inicia|expande|abre)|crece|innova|emprende|"
    r"concurso\s+(de\s+)?(proyecto|innovaci[óo]n|emprendimiento|startup|i+d|i\+d|investigaci[óo]n)|"
    r"programa\s+(de\s+)?(financiamiento|fondos|subsidio|apoyo|fomento|inversi[óo]n|desarrollo)|"
    r"beca\s+(de\s+)?(investigaci[óo]n|postdoctoral|doctorado|mag[ií]ster)|"
    r"proyecto\s+(de\s+)?(i\+d|i+d|innovaci[óo]n|investigaci[óo]n|emprendimiento)|"
    r"convocatoria\s+(de\s+)?(fondos|financiamiento|proyecto|investigaci[óo]n|innovaci[óo]n)"
    r")\b",
    re.IGNORECASE,
)


def es_financiamiento_proyecto(titulo: str, descripcion: str | None = None) -> bool:
    """Determina si un item representa financiamiento a proyectos.

    Lógica:
    1. Si el título contiene patrones de exclusión administrativa → False
    2. Si el título o descripción contiene patrones positivos de financiamiento → True
    3. Si no hay señal positiva ni negativa → True (conservador: se asume relevante)
    """
    texto = titulo
    if descripcion:
        texto = f"{titulo} {descripcion}"

    if _EXCLUSION_PATTERNS.search(titulo):
        return False

    if _FUNDING_POSITIVE_PATTERNS.search(texto):
        return True

    return True


def es_fecha_titulo_reciente(titulo: str, meses_ventana: int = 3) -> bool:
    """Verifica que el año mencionado en el título no sea anterior a la ventana.

    Si no hay año en el título, devuelve True (conservador).
    Si hay año y es anterior a (ahora - meses_ventana), devuelve False.
    """
    from datetime import UTC, datetime, timedelta

    fecha_minima = datetime.now(UTC) - timedelta(days=meses_ventana * 30)
    anio_minimo = fecha_minima.year

    matches = _YEAR_IN_TITLE.findall(titulo)
    for anio_str in matches:
        anio = int(anio_str)
        if anio < anio_minimo:
            return False

    return True


def filtrar_relevantes_raw(
    items: list[dict[str, Any]],
    meses_ventana: int = 3,
) -> list[dict[str, Any]]:
    """Filtra items crudos (dict) dejando solo los que son financiamiento a proyectos.

    Se usa en el pipeline antes de la hidratación a Convocatoria.
    """
    relevantes: list[dict[str, Any]] = []
    descartadas_exclusion = 0
    descartadas_fecha = 0

    for item in items:
        titulo = str(item.get("titulo") or "")
        descripcion = item.get("descripcion")
        descripcion_str = str(descripcion) if descripcion else None

        if not es_financiamiento_proyecto(titulo, descripcion_str):
            descartadas_exclusion += 1
            logger.debug("Descartada por exclusión de relevancia", titulo=titulo[:80])
            continue

        if not es_fecha_titulo_reciente(titulo, meses_ventana):
            descartadas_fecha += 1
            logger.debug("Descartada por año en título fuera de ventana", titulo=titulo[:80])
            continue

        relevantes.append(item)

    descartadas = descartadas_exclusion + descartadas_fecha
    if descartadas > 0:
        logger.info(
            "Filtro de relevancia aplicado",
            total=len(items),
            relevantes=len(relevantes),
            descartadas=descartadas,
            por_exclusion=descartadas_exclusion,
            por_fecha_titulo=descartadas_fecha,
        )

    return relevantes


def filtrar_relevantes(
    convocatorias: list[Any],
    meses_ventana: int = 3,
) -> list[Any]:
    """Filtra entidades Convocatoria dejando solo las que son financiamiento a proyectos."""
    relevantes: list[Any] = []
    descartadas = 0

    for c in convocatorias:
        titulo = getattr(c, "titulo", "")
        descripcion = getattr(c, "descripcion", None)
        descripcion_str = str(descripcion) if descripcion else None

        if not es_financiamiento_proyecto(titulo, descripcion_str):
            descartadas += 1
            logger.debug("Descartada por exclusión de relevancia", titulo=titulo[:80])
            continue

        if not es_fecha_titulo_reciente(titulo, meses_ventana):
            descartadas += 1
            logger.debug("Descartada por año en título fuera de ventana", titulo=titulo[:80])
            continue

        relevantes.append(c)

    if descartadas > 0:
        logger.info(
            "Filtro de relevancia aplicado (entidades)",
            total=len(convocatorias),
            relevantes=len(relevantes),
            descartadas=descartadas,
        )

    return relevantes
