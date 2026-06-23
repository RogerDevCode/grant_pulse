import asyncio
import json
from src.infra.db.connection import engine
from sqlalchemy import text

async def main():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT contenido_crudo FROM snapshots WHERE fuente_id = (SELECT id FROM fuentes WHERE nombre = 'CORFO') ORDER BY fecha_captura DESC LIMIT 1"))
        row = result.fetchone()
        data = json.loads(row.contenido_crudo)
        print("Metadata:", data.get("metadata"))

asyncio.run(main())
