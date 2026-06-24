import asyncio

from sqlalchemy import text

from src.infra.db.connection import engine


async def main():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT id, titulo, regiones, estado_enriquecimiento, detalles_llm FROM convocatorias WHERE id IN (16, 17, 18)"))
        rows = result.fetchall()
        for r in rows:
            print(f"ID: {r.id} | Regiones: {r.regiones} | Titulo: {r.titulo[:50]}")
            print(f"Estado Enriquecimiento: {r.estado_enriquecimiento}")
            print(f"Detalles LLM: {r.detalles_llm}")
            print("-" * 40)

asyncio.run(main())
