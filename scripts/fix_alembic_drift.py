import asyncio
import os
import subprocess
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set. Skipping alembic drift fix.")
        return

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url)
    try:
        async with engine.connect() as conn:
            # Check if alembic_version has rows
            res = await conn.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'alembic_version')"))
            if res.scalar():
                res = await conn.execute(text("SELECT COUNT(*) FROM alembic_version"))
                count = res.scalar()
                if count is not None and count > 0:
                    print("Alembic is already tracking the database.")
                    return

            res = await conn.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'fuentes')"))
            if not res.scalar():
                print("Database is empty. Alembic will initialize it.")
                return

            print("Database has tables but no alembic tracking. Detecting schema state...")

            # Check for columns to determine the latest state
            res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'convocatorias' AND column_name = 'url_check_failures'"))
            has_url_check = res.scalar() is not None

            res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'convocatorias' AND column_name = 'estado_enriquecimiento'"))
            has_enriquecimiento = res.scalar() is not None

            res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'convocatorias' AND column_name = 'regiones'"))
            has_regiones = res.scalar() is not None

    finally:
        await engine.dispose()

    target_revision = "0001"
    if has_url_check:
        target_revision = "7efda2419024"
    elif has_enriquecimiento:
        target_revision = "0338c8d1d224"
    elif has_regiones:
        target_revision = "05e8210785b9"

    print(f"Stamping database to revision {target_revision}")
    subprocess.run([sys.executable, "-m", "alembic", "stamp", target_revision], check=True)

if __name__ == "__main__":
    asyncio.run(main())
