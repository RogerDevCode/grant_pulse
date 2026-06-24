import asyncio
import json

from src.infra.llm.client import build_llm_client
from src.infra.workers.enrichment_worker import HttpxPageFetcher


async def main():
    fetcher = HttpxPageFetcher()
    url = "https://www.corfo.gob.cl/sites/cpp/convocatoria/semilla-inicia-biobio-2026/"
    print("Fetching HTML...")
    html = await fetcher.fetch_html(url)

    print("Calling LLM...")
    llm = build_llm_client()
    result = await llm.extract_single_detail(
        html_content=html,
        base_url=url,
        institution_name="CORFO",
        institution_hint="Los programas Semilla Inicia están orientados a emprendedores en etapas tempranas."
    )
    print("Result:")
    print(json.dumps(result, indent=2))

asyncio.run(main())
