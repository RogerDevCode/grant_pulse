import asyncio
import os

import httpx
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")

async def main():
    print("1. Creando sesión de Cloudflare CDP...")
    url_create = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/browser-rendering/devtools/browser?keep_alive=600000"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url_create, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    ws_url = data.get("webSocketDebuggerUrl")
    session_id = data.get("sessionId")
    print(f"Sesión creada: {session_id}")
    print(f"WS URL: {ws_url}")

    print("\n2. Conectando Playwright vía CDP...")
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(ws_url, headers=headers)
        # Cloudflare docs dicen que la sesión suele estar vacía, abramos un contexto
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()

        target_url = "https://www.corfo.gob.cl/sites/cpp/programasyconvocatorias/"
        print(f"Navegando a {target_url} ...")
        await page.goto(target_url, wait_until="domcontentloaded")

        print("Esperando a que la red se calme...")
        await page.wait_for_timeout(5000)

        items_selector = ".caja-resultados_uno"

        initial_items = await page.locator(items_selector).count()
        print(f"Items iniciales cargados: {initial_items}")

        # Vamos a buscar el botón de 'Ver más' o 'Cargar más'
        # Podría ser un <button> o <a> con texto como "Ver más", "Cargar más", "Siguiente"
        print("Intentando cargar más items...")
        clicks = 0
        while clicks < 5:
            load_more_btn = page.get_by_text("Siguiente", exact=True)

            if await load_more_btn.is_visible() and await load_more_btn.is_enabled():
                print("Click en 'Siguiente'...")
                await load_more_btn.click()
                print("Esperando la red para la siguiente página...")
                await page.wait_for_timeout(4000) # esperar que el ajax vuelva
                clicks += 1
            else:
                print("No se encontró el botón 'Siguiente' o está deshabilitado.")
                break

        final_items = await page.locator(items_selector).count()
        print(f"Items totales cargados después de iterar: {final_items}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
