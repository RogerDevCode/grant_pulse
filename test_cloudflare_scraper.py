import asyncio
import os
import sys

import yaml
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(__file__))

from src.core.domain.entities import Fuente, RulesConfig
from src.infra.scraping.cloudflare_scraper import CloudflareBrowserScraper


async def main():
    # Cargar las reglas de CORFO
    rules_path = os.path.join(os.path.dirname(__file__), "rules", "corfo.yaml")
    with open(rules_path, encoding="utf-8") as f:
        rules_dict = yaml.safe_load(f)

    config = RulesConfig(**rules_dict)

    fuente = Fuente(
        id=1,
        nombre="CORFO Test Cloudflare",
        url_base="https://www.corfo.gob.cl",
        activa=True,
        configuracion_reglas=config
    )

    scraper = CloudflareBrowserScraper()

    print("Iniciando fetch con CloudflareBrowserScraper...")
    try:
        snapshot = await scraper.fetch(fuente)
        print(f"HTML obtenido. Longitud: {len(snapshot.contenido_crudo)} caracteres.")
    except Exception as e:
        print(f"Error en fetch: {e}")
        return

    print("Iniciando extracción delegada a HtmlStaticScraper...")
    try:
        items = await scraper.extract(snapshot, fuente)
        print(f"\n¡Éxito! El scraper extrajo {len(items)} convocatorias:")
        for idx, item in enumerate(items, 1):
            print(f"\n--- Convocatoria {idx} ---")
            for key, value in item.items():
                print(f"{key}: {value}")
    except Exception as e:
        print(f"Error en extracción: {e}")

if __name__ == "__main__":
    asyncio.run(main())
