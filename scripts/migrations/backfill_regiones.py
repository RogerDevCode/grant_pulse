"""Script de backfill de regiones para convocatorias existentes.

Idempotente: ejecutable múltiples veces sin efecto acumulativo.
Solo procesa convocatorias con regiones vacías.

Uso:
    python scripts/migrations/backfill_regiones.py
"""

import asyncio
import sys
from pathlib import Path

# Agregar raíz del proyecto al path
root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root))

from sqlalchemy import String, cast, select

from src.core.application.region_inferrer import inferir_regiones
from src.infra.db.connection import AsyncSessionLocal
from src.infra.db.models import ConvocatoriaORM


async def backfill_regiones():
    """Asigna regiones a convocatorias existentes usando inferencia heurística."""
    async with AsyncSessionLocal() as session:
        # PostgreSQL no permite comparar JSON directamente, usar cast
        stmt = select(ConvocatoriaORM).where(
            (ConvocatoriaORM.regiones.is_(None)) |
            (cast(ConvocatoriaORM.regiones, String) == '[]')
        )
        result = await session.execute(stmt)
        convocatorias = result.scalars().all()

        total = len(convocatorias)
        actualizadas = 0

        for conv in convocatorias:
            regiones = inferir_regiones(conv.titulo, conv.descripcion or "")
            if regiones:
                conv.regiones = regiones
                actualizadas += 1

        if actualizadas > 0:
            await session.commit()

        print(f"Procesadas: {total}")
        print(f"Actualizadas con región: {actualizadas}")
        print(f"Sin región detectable: {total - actualizadas}")


if __name__ == "__main__":
    asyncio.run(backfill_regiones())
