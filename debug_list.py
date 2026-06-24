import asyncio

from sqlalchemy import String, cast, func, select

from src.infra.db.connection import AsyncSessionLocal
from src.infra.db.models import ConvocatoriaORM, FuenteORM


async def run():
    async with AsyncSessionLocal() as session:
        query = select(ConvocatoriaORM, FuenteORM.nombre).join(FuenteORM, ConvocatoriaORM.fuente_id == FuenteORM.id)

        query = query.where(
            func.coalesce(cast(ConvocatoriaORM.metadatos["url_check_failed"], String), "false") != "true"
        )

        # Test ordering which is unique to list_convocatorias
        from datetime import UTC, datetime
        now = datetime.now(UTC)
        query = query.order_by(
            func.coalesce(ConvocatoriaORM.fecha_cierre < now, False).asc(),
            ConvocatoriaORM.fecha_cierre.asc().nullslast()
        )
        query = query.limit(10)

        try:
            res = await session.execute(query)
            rows = res.all()
            print(f"List Query Result: {len(rows)} rows")
        except Exception as e:
            print("ERROR:", str(e))

if __name__ == "__main__":
    asyncio.run(run())
