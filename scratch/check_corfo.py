import asyncio

from sqlalchemy import text

from src.infra.db.connection import engine


async def main():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT id, titulo, regiones, identificador_externo FROM convocatorias WHERE fuente_id = (SELECT id FROM fuentes WHERE nombre = 'CORFO')"))
        rows = result.fetchall()
        print(f"Total rows for CORFO: {len(rows)}")
        for r in rows:
            print(f"ID: {r.id} | Titulo: {r.titulo[:30]} | Regiones: {r.regiones} | ExtID: {r.identificador_externo}")

asyncio.run(main())
