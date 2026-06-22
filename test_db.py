import asyncio

from sqlalchemy import text

from src.infra.db.connection import AsyncSessionLocal


async def main():
    async with AsyncSessionLocal() as session:
        snapshots = await session.execute(text("SELECT id, fuente_id, estado_ejecucion, length(contenido_crudo) FROM snapshots"))
        print("Snapshots:", snapshots.fetchall())

        convs = await session.execute(text("SELECT id, fuente_id, identificador_externo FROM convocatorias"))
        print("Convocatorias:", convs.fetchall())

asyncio.run(main())
