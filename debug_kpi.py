import asyncio

from sqlalchemy import String, cast, func, select

from src.infra.db.connection import AsyncSessionLocal
from src.infra.db.models import ConvocatoriaORM


async def run():
    async with AsyncSessionLocal() as session:
        query = select(func.count(ConvocatoriaORM.id)).where(
            func.coalesce(cast(ConvocatoriaORM.metadatos["url_check_failed"], String), "false") != "true"
        )
        try:
            res = await session.execute(query)
            print("KPI Query Result:", res.scalar())
        except Exception as e:
            print("ERROR:", str(e))

if __name__ == "__main__":
    asyncio.run(run())
