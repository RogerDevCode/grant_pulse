import asyncio

from sqlalchemy import select, text

from src.infra.db.connection import AsyncSessionLocal, engine
from src.infra.db.models import ConvocatoriaORM
from src.infra.workers.enrichment_worker import run_enrichment_worker


async def main():
    print("Resetting enrichment status for CORFO ABIERTO records...")
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE convocatorias SET estado_enriquecimiento = 'PENDIENTE', detalles_llm = NULL WHERE fuente_id = 2 AND estado = 'ABIERTO' AND regiones::text LIKE '%Biobío%'"))

    print("Running enrichment worker for 3 records...")
    await run_enrichment_worker(batch_size=3)

    print("Verifying results in DB...")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ConvocatoriaORM)
            .where(ConvocatoriaORM.fuente_id == 2)
            .where(text("regiones::text LIKE '%Biobío%'"))
            .limit(5)
        )
        for r in result.scalars():
            print(f"ID: {r.id} | Titulo: {r.titulo[:50]} | Enriquecido: {r.estado_enriquecimiento}")
            print(f"Detalles LLM: {r.detalles_llm}")

asyncio.run(main())
