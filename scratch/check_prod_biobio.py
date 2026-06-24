import asyncio

import httpx


async def check():
    url_base = "https://grantpulse-production.up.railway.app/api/v1/convocatorias"

    async with httpx.AsyncClient() as client:
        # Check list
        r_list = await client.get(f"{url_base}?region=Biobío&fuente_nombre=CORFO")
        data_list = r_list.json()

        # Check count
        r_count = await client.get(f"{url_base}/count?region=Biobío&fuente_nombre=CORFO")
        data_count = r_count.json()

        print(f"Count endpoint says: {data_count.get('total')}")
        print(f"List endpoint returned {len(data_list)} items")
        for i, item in enumerate(data_list):
            print(f"{i+1}. {item['titulo']} - Regiones: {item['regiones']}")

asyncio.run(check())
