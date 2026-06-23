import asyncio
from src.infra.db.connection import engine
from sqlalchemy import text

async def main():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT id, titulo, descripcion, regiones FROM convocatorias WHERE fuente_id = 2"))
        rows = result.fetchall()
        for r in rows:
            print(f"ID: {r.id} | Regiones: {r.regiones} | Titulo: {r.titulo[:80]}")

asyncio.run(main())
