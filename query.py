import asyncio
import os

from sqlalchemy import text
from src.infra.db.session import async_session

os.environ["DATABASE_URL"] = "postgresql+asyncpg://grantpulse:grantpulse@localhost:5432/grantpulse"

async def main():
    try:
        async with async_session() as session:
            result = await session.execute(text("SELECT count(*) FROM convocatorias"))
            print(f"Total: {result.scalar()}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
