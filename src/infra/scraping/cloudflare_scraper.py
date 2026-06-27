import hashlib
import os
from datetime import UTC, datetime
from typing import Any

import httpx

from src.core.domain.entities import Fuente, Snapshot
from src.core.domain.exceptions import NetworkError
from src.core.domain.ports import ScraperPort
from src.infra.logging import get_logger
from src.infra.scraping.html_static import HtmlStaticScraper

logger = get_logger(__name__)


class CloudflareBrowserScraper(ScraperPort):
    """
    Scraper que utiliza Cloudflare Browser Rendering (Workers Browser Run) para
    obtener el HTML final tras la ejecución de JavaScript.

    Para la fase de extracción, delega en HtmlStaticScraper para aplicar los
    selectores CSS al HTML renderizado.
    """

    def __init__(self, timeout: int = 60) -> None:
        self._timeout = timeout
        self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.api_token = os.getenv("CLOUDFLARE_API_TOKEN")

    async def fetch(self, fuente: Fuente) -> Snapshot:
        url = str(fuente.configuracion_reglas.url_busqueda)
        logger.info("CloudflareBrowserScraper: realizando fetch via Cloudflare", url=url, fuente=fuente.nombre)

        if not self.account_id or not self.api_token:
            msg = "Faltan variables CLOUDFLARE_ACCOUNT_ID o CLOUDFLARE_API_TOKEN"
            logger.error(msg)
            raise NetworkError(msg)

        cloudflare_url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/browser-rendering/content"
        headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}

        # Opciones más adecuadas para CORFO y sitios SPA (Single Page Applications)
        # waitUntil: "networkidle2" asegura que se esperen las llamadas AJAX y carga de la tabla
        payload = {"url": url, "gotoOptions": {"waitUntil": "networkidle2", "timeout": 45000}}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(cloudflare_url, headers=headers, json=payload)
                response.raise_for_status()

                # Cloudflare /content endpoint retorna el HTML directamente si pedimos bien,
                # o envuelto en JSON dependiendo del content-type
                if response.headers.get("content-type", "").startswith("text/html"):
                    html_content = response.text
                else:
                    data = response.json()
                    if "result" in data and isinstance(data["result"], dict) and "html" in data["result"]:
                        html_content = data["result"]["html"]
                    elif "result" in data and isinstance(data["result"], str):
                        html_content = data["result"]
                    else:
                        html_content = str(data)

        except Exception as e:
            msg = f"Error en fetch con Cloudflare Browser Run para {url}: {e}"
            logger.error(msg, exc=e)
            raise NetworkError(msg) from e

        content_hash = hashlib.sha256(html_content.encode("utf-8")).hexdigest()

        return Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=html_content,
            hash_contenido=content_hash,
            estado_ejecucion="SUCCESS",
        )

    async def extract(
        self,
        snapshot: Snapshot,
        fuente: Fuente,
        **kwargs: Any,
    ) -> list[dict[str, str | None]]:
        """
        Extrae items de convocatoria. En vez de reinventar la rueda, podemos usar
        la lógica de HtmlStaticScraper internamente para aplicar los selectores CSS.
        """
        # Delegamos la extracción al scraper HTML estático (BS4 + CSS Selectors)
        # ya que Cloudflare ya nos hizo el favor de darnos el DOM final
        extractor = HtmlStaticScraper()
        return await extractor.extract(snapshot, fuente, **kwargs)
