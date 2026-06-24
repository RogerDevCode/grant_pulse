import asyncio
import json

from bs4 import BeautifulSoup
from sqlalchemy import text

from src.infra.db.connection import engine


async def main():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT contenido_crudo FROM snapshots WHERE fuente_id = (SELECT id FROM fuentes WHERE nombre = 'CORFO') ORDER BY fecha_captura DESC LIMIT 1"))
        row = result.fetchone()
        data = json.loads(row.contenido_crudo)
        html_content = data.get("html", "")

        soup = BeautifulSoup(html_content, 'html.parser')
        items = soup.select(".caja-resultados_uno")
        for item in items:
            title_node = item.select_one("h4")
            estado_node = item.select_one("h6")
            cierre_node = item.select_one(".cierre span")

            if title_node and ("INNOVA" in title_node.text.upper() or "SEMILLA" in title_node.text.upper()):
                print(f"Title: {title_node.text.strip()}")
                if cierre_node:
                    print(f"Cierre: {cierre_node.text.strip()}")
                print("---")

asyncio.run(main())
