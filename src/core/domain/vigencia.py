"""
Servicio de dominio: filtro de vigencia de convocatorias.

Regla de negocio: una convocatoria es vigente si:
1. Su estado explícito es ABIERTO / PROXIMAMENTE (no CERRADO, ADJUDICADO, SUSPENDIDO)
2. O, si no hay estado explícito, su fecha de cierre no ha pasado
3. O, si no hay fecha de cierre ni estado, se asume vigente (conservador)

Esto se aplica como post-procesamiento después de la extracción,
antes de persistir y antes de notificar.
"""

from datetime import UTC, datetime
from typing import Any

from src.core.domain.entities import Convocatoria
from src.core.domain.fecha_utils import parse_fecha_chilena
from src.infra.logging import get_logger

logger = get_logger(__name__)

_ESTADOS_NO_VIGENTES = frozenset({"CERRADO", "CERRADA", "ADJUDICADO", "ADJUDICADA", "SUSPENDIDO", "SUSPENDIDA", "FINALIZADO", "FINALIZADA"})
_ESTADOS_VIGENTES = frozenset({"ABIERTO", "ABIERTA", "PROXIMAMENTE", "VIGENTE", "PUBLISH"})


def es_convocatoria_vigente(
    convocatoria: Convocatoria,
    referencia: datetime | None = None,
) -> bool:
    """
    Determina si una convocatoria está vigente a la fecha de referencia.

    Reglas (en orden de precedencia):
    1. Estado explícito no vigente → False
    2. Estado explícito vigente → True
    3. Fecha de cierre pasada → False
    4. Sin estado ni fecha de cierre → True (conservador: se asume vigente)
    """
    ahora = referencia or datetime.now(UTC)
    estado = (convocatoria.estado or "").strip().upper()

    if estado in _ESTADOS_NO_VIGENTES:
        return False

    if estado in _ESTADOS_VIGENTES:
        if convocatoria.fecha_cierre is not None and convocatoria.fecha_cierre < ahora:
            logger.warning(
                "Convocatoria con estado vigente pero fecha de cierre pasada",
                titulo=convocatoria.titulo[:60],
                estado=estado,
                fecha_cierre=str(convocatoria.fecha_cierre),
            )
        return True

    if convocatoria.fecha_cierre is not None:
        return convocatoria.fecha_cierre >= ahora

    return True


def filtrar_vigentes(
    convocatorias: list[Convocatoria],
    referencia: datetime | None = None,
) -> list[Convocatoria]:
    """
    Filtra una lista de convocatorias dejando solo las vigentes.

    Registra métricas de cuántas se descartan y por qué razón.
    """
    ahora = referencia or datetime.now(UTC)
    vigentes: list[Convocatoria] = []
    descartadas_estado = 0
    descartadas_fecha = 0

    for c in convocatorias:
        estado = (c.estado or "").strip().upper()

        if estado in _ESTADOS_NO_VIGENTES:
            descartadas_estado += 1
            logger.debug("Descartada por estado", titulo=c.titulo[:60], estado=estado)
            continue

        if estado in _ESTADOS_VIGENTES:
            vigentes.append(c)
            continue

        if c.fecha_cierre is not None and c.fecha_cierre < ahora:
            descartadas_fecha += 1
            logger.debug("Descartada por fecha de cierre pasada", titulo=c.titulo[:60], fecha_cierre=str(c.fecha_cierre))
            continue

        vigentes.append(c)

    descartadas = descartadas_estado + descartadas_fecha
    if descartadas > 0:
        logger.info(
            "Filtro de vigencia aplicado",
            total=len(convocatorias),
            vigentes=len(vigentes),
            descartadas=descartadas,
            por_estado=descartadas_estado,
            por_fecha=descartadas_fecha,
        )

    return vigentes


def filtrar_vigentes_raw(
    items: list[dict[str, Any]],
    referencia: datetime | None = None,
) -> list[dict[str, Any]]:
    """
    Filtra items crudos (dict) dejando solo los vigentes.

    Se usa en el pipeline antes de la hidratación a Convocatoria,
    cuando los items vienen como dicts sin validar.
    """
    ahora = referencia or datetime.now(UTC)
    vigentes: list[dict[str, Any]] = []
    descartadas = 0

    for item in items:
        estado = str(item.get("estado") or "").strip().upper()

        if estado in _ESTADOS_NO_VIGENTES:
            descartadas += 1
            continue

        if estado not in _ESTADOS_VIGENTES:
            fecha_cierre_str = item.get("fecha_cierre")
            if fecha_cierre_str is not None:
                fecha_cierre = parse_fecha_chilena(str(fecha_cierre_str))
                if fecha_cierre is not None and fecha_cierre < ahora:
                    descartadas += 1
                    continue

        vigentes.append(item)

    if descartadas > 0:
        logger.info(
            "Filtro de vigencia raw aplicado",
            total=len(items),
            vigentes=len(vigentes),
            descartadas=descartadas,
        )

    return vigentes
