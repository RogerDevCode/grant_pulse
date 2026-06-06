"""
Servicio de dominio: filtro de vigencia de convocatorias.

Regla de negocio: una convocatoria es vigente si:
1. Su estado explícito es ABIERTO / PROXIMAMENTE (no CERRADO, ADJUDICADO, SUSPENDIDO)
2. O, si no hay estado explícito, su fecha de cierre no ha pasado
3. O, si no hay fecha de cierre ni estado, se asume vigente (conservador)

VENTANA TEMPORAL (meses_ventana):
4. Si la fecha de cierre existe y es anterior a (ahora - meses_ventana), se descarta
   aunque el estado sea vigente. Esto elimina convocatorias antiguas
   que permanecen "ABIERTO" pero ya no son operativamente relevantes.

Esto se aplica como post-procesamiento después de la extracción,
antes de persistir y antes de notificar.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from src.core.domain.entities import Convocatoria
from src.core.domain.estado_normalizer import normalize_estado
from src.core.domain.fecha_utils import parse_fecha_chilena
from src.infra.logging import get_logger

logger = get_logger(__name__)

_ESTADOS_NO_VIGENTES = frozenset({"CERRADO", "ADJUDICADO", "SUSPENDIDO", "FINALIZADO"})
_ESTADOS_VIGENTES = frozenset({"ABIERTO", "PROXIMAMENTE"})
MESES_VENTANA_DEFAULT = 3


def es_convocatoria_vigente(
    convocatoria: Convocatoria,
    referencia: datetime | None = None,
    meses_ventana: int = MESES_VENTANA_DEFAULT,
) -> bool:
    """
    Determina si una convocatoria está vigente a la fecha de referencia.

    Reglas (en orden de precedencia):
    1. Estado explícito no vigente → False
    2. Estado explícito vigente → True (salvo ventana temporal, regla 5)
    3. Fecha de cierre pasada → False
    4. Sin estado ni fecha de cierre → True (conservador: se asume vigente)
    5. Fecha de cierre anterior a (referencia - meses_ventana) → False
    """
    ahora = referencia or datetime.now(UTC)
    estado = normalize_estado(convocatoria.estado)

    if estado in _ESTADOS_NO_VIGENTES:
        return False

    if estado in _ESTADOS_VIGENTES:
        if convocatoria.fecha_cierre is not None and meses_ventana > 0:
            limite_ventana = ahora - timedelta(days=meses_ventana * 30)
            if convocatoria.fecha_cierre < limite_ventana:
                return False
            if convocatoria.fecha_cierre < ahora:
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
    meses_ventana: int = MESES_VENTANA_DEFAULT,
) -> list[Convocatoria]:
    """
    Filtra una lista de convocatorias dejando solo las vigentes.

    Registra métricas de cuántas se descartan y por qué razón.
    """
    ahora = referencia or datetime.now(UTC)
    vigentes: list[Convocatoria] = []
    descartadas_estado = 0
    descartadas_fecha = 0
    descartadas_ventana = 0

    for c in convocatorias:
        estado = normalize_estado(c.estado)

        if estado in _ESTADOS_NO_VIGENTES:
            descartadas_estado += 1
            logger.debug("Descartada por estado", titulo=c.titulo[:60], estado=estado)
            continue

        if estado in _ESTADOS_VIGENTES:
            if c.fecha_cierre is not None and meses_ventana > 0:
                limite_ventana = ahora - timedelta(days=meses_ventana * 30)
                if c.fecha_cierre < limite_ventana:
                    descartadas_ventana += 1
                    logger.debug(
                        "Descartada por ventana temporal",
                        titulo=c.titulo[:60],
                        fecha_cierre=str(c.fecha_cierre),
                        limite=str(limite_ventana.date()),
                    )
                    continue
            vigentes.append(c)
            continue

        if c.fecha_cierre is not None and c.fecha_cierre < ahora:
            descartadas_fecha += 1
            logger.debug("Descartada por fecha de cierre pasada", titulo=c.titulo[:60], fecha_cierre=str(c.fecha_cierre))
            continue

        vigentes.append(c)

    descartadas = descartadas_estado + descartadas_fecha + descartadas_ventana
    if descartadas > 0:
        logger.info(
            "Filtro de vigencia aplicado",
            total=len(convocatorias),
            vigentes=len(vigentes),
            descartadas=descartadas,
            por_estado=descartadas_estado,
            por_fecha=descartadas_fecha,
            por_ventana=descartadas_ventana,
        )

    return vigentes


def filtrar_vigentes_raw(
    items: list[dict[str, Any]],
    referencia: datetime | None = None,
    meses_ventana: int = MESES_VENTANA_DEFAULT,
) -> list[dict[str, Any]]:
    """
    Filtra items crudos (dict) dejando solo los vigentes.

    Se usa en el pipeline antes de la hidratación a Convocatoria,
    cuando los items vienen como dicts sin validar.
    """
    ahora = referencia or datetime.now(UTC)
    vigentes: list[dict[str, Any]] = []
    descartadas = 0

    limite_ventana = ahora - timedelta(days=meses_ventana * 30) if meses_ventana > 0 else None

    for item in items:
        estado = normalize_estado(item.get("estado"))

        if estado in _ESTADOS_NO_VIGENTES:
            descartadas += 1
            continue

        if estado in _ESTADOS_VIGENTES:
            fecha_cierre_str = item.get("fecha_cierre")
            if fecha_cierre_str is not None and limite_ventana is not None:
                fecha_cierre = parse_fecha_chilena(str(fecha_cierre_str))
                if fecha_cierre is not None and fecha_cierre < limite_ventana:
                    descartadas += 1
                    continue
            vigentes.append(item)
            continue

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
