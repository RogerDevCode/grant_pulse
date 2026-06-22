import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.infra.config import settings


async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        tables = [
            "config_notificaciones",
            "audit_logs",
            "notificaciones",
            "notificacion_resultados",
            "suscripciones",
            "historial_cambios",
            "convocatorias",
            "snapshots",
            "fuentes",
            "alembic_version"
        ]
        for t in tables:
            await conn.execute(text(f"DROP TABLE IF EXISTS {t} CASCADE"))
    print("Tables dropped.")

if __name__ == "__main__":
    asyncio.run(main())
