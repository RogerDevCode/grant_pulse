import asyncio, asyncpg
from src.infra.config import settings

async def main():
    url = settings.DATABASE_URL.replace('+asyncpg', '')
    conn = await asyncpg.connect(url)
    await conn.execute('DROP TABLE IF EXISTS alembic_version;')
    await conn.close()

asyncio.run(main())
