"""
Módulo para la generación de reportes de calidad y salud de las fuentes.
"""

from datetime import UTC, datetime
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infra.db.models import ConvocatoriaORM, FuenteORM
from src.infra.logging import get_logger

logger = get_logger(__name__)


async def generar_reporte_calidad(session: AsyncSession, output_path: Path) -> None:
    """
    Genera un reporte Markdown con el porcentaje de campos completados
    por cada fuente (tasa de éxito de extracción de metadatos).
    """
    logger.info("Generando reporte de calidad", output_path=str(output_path))

    # Obtener todas las fuentes activas
    query_fuentes = select(FuenteORM).where(FuenteORM.activa)
    res_fuentes = await session.execute(query_fuentes)
    fuentes = res_fuentes.scalars().all()

    lineas = [
        "# Reporte de Calidad de Scraping (Data Quality)",
        f"Generado el: {datetime.now(UTC).isoformat()}",
        "",
        "| Fuente | Estrategia | Total Items | % Cierre | % Monto | % Región | % Desc |",
        "|--------|------------|-------------|----------|---------|----------|--------|",
    ]

    for fuente in sorted(fuentes, key=lambda f: f.nombre):
        # Obtener métricas para esta fuente
        q_stats = select(
            func.count(ConvocatoriaORM.id).label("total"),
            func.count(ConvocatoriaORM.fecha_cierre).label("con_cierre"),
            func.count(ConvocatoriaORM.monto).label("con_monto"),
            func.count(ConvocatoriaORM.region).label("con_region"),
            func.count(ConvocatoriaORM.descripcion).label("con_desc"),
        ).where(ConvocatoriaORM.fuente_id == fuente.id)

        res_stats = await session.execute(q_stats)
        stats = res_stats.first()

        try:
            config = yaml.safe_load(fuente.configuracion_yaml)
            estrategia = config.get("estrategia", "desconocida")
        except Exception:
            estrategia = "error"

        if not stats or stats.total == 0:
            lineas.append(f"| {fuente.nombre} | `{estrategia}` | 0 | - | - | - | - |")
            continue

        total = stats.total
        p_cierre = (stats.con_cierre / total) * 100
        p_monto = (stats.con_monto / total) * 100
        p_region = (stats.con_region / total) * 100
        p_desc = (stats.con_desc / total) * 100

        lineas.append(
            f"| {fuente.nombre} | `{estrategia}` | {total} | {p_cierre:.1f}% | {p_monto:.1f}% | {p_region:.1f}% | {p_desc:.1f}% |"
        )

    reporte_str = "\n".join(lineas)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(reporte_str, encoding="utf-8")
    logger.info("Reporte de calidad guardado exitosamente.")
