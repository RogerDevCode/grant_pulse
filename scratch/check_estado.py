import asyncio
from src.infra.db.connection import engine
from sqlalchemy import text

async def main():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT id, titulo, estado, fecha_cierre FROM convocatorias WHERE titulo ILIKE '%biobio%' OR titulo ILIKE '%biobío%' OR regiones::text ILIKE '%biobío%'"))
        rows = result.fetchall()
        for r in rows:
            print(f"ID: {r.id} | Titulo: {r.titulo[:30]} | Estado: {r.estado} | Cierre: {r.fecha_cierre}")

asyncio.run(main())
