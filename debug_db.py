import asyncio

from src.infra.db.connection import AsyncSessionLocal
from src.infra.db.repository import SQLFuenteRepository


async def main():
    async with AsyncSessionLocal() as session:
        repo = SQLFuenteRepository(session)
        f = await repo.get_by_nombre("CORFO")
        print("f:", f)
        if f: print("f.id:", f.id, type(f.id))

if __name__ == "__main__":
    asyncio.run(main())
