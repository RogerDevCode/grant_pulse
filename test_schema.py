import asyncio

from sqlalchemy import text

from src.infra.db.connection import AsyncSessionLocal


async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'fuentes';"))
        for row in result.fetchall():
            print(row)

if __name__ == "__main__":
    asyncio.run(main())
