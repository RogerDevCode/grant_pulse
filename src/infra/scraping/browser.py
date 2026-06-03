"""
Implementación del motor de scraping basado en Browser Automation (Playwright).
Permite renderizar JavaScript y evadir protecciones anti-bot básicas.
"""

import hashlib
from datetime import UTC, datetime
from typing import Any, cast

from playwright.async_api import async_playwright  # pyright: ignore[reportMissingImports]

from src.core.domain.entities import Fuente, Snapshot
from src.core.domain.exceptions import NetworkError
from src.core.domain.ports import ScraperPort
from src.infra.logging import get_logger

logger = get_logger(__name__)


class PlaywrightScraper(ScraperPort):
    """
    Adaptador de scraping que utiliza un navegador real (headless)
    para interactuar con portales complejos.
    """

    def __init__(self, timeout: int = 30000) -> None:
        self._timeout = timeout

    async def fetch(self, fuente: Fuente) -> Snapshot:
        url = str(fuente.configuracion_reglas.url_busqueda)
        logger.info("Iniciando fetch con navegador (Playwright)", url=url)

        from src.infra.config import settings

        proxy_config = None
        if settings.PROXY_URL:
            proxy_config = {"server": settings.PROXY_URL}
            if settings.PROXY_USER and settings.PROXY_PASS:
                proxy_config["username"] = settings.PROXY_USER
                proxy_config["password"] = settings.PROXY_PASS
            logger.info("Usando proxy para navegación", server=settings.PROXY_URL)

        async with async_playwright() as p:
            # Lanzamos Chromium con o sin proxy
            browser = await p.chromium.launch(
                headless=True,
                proxy=cast(Any, proxy_config),
            )  # pyright: ignore[reportUnknownMemberType]

            # Configuramos un contexto con User-Agent realista
            context = await browser.new_context(  # pyright: ignore[reportUnknownMemberType]
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720},
            )

            page = await context.new_page()  # pyright: ignore[reportUnknownMemberType]

            try:
                # Navegar a la URL
                response = await page.goto(url, wait_until="networkidle", timeout=self._timeout)  # pyright: ignore[reportUnknownMemberType]

                if not response or response.status >= 400:  # pyright: ignore[reportUnknownMemberType]
                    status = response.status if response else "Unknown"  # pyright: ignore[reportUnknownMemberType]
                    raise NetworkError(f"El navegador recibió un error HTTP {status} al acceder a {url}")

                # Esperar un momento extra por si hay carga de JS lenta (opcional)
                # await page.wait_for_timeout(2000)

                # Obtener el contenido HTML final (renderizado)
                html_content: str = await page.content()  # pyright: ignore[reportUnknownMemberType]

            except Exception as e:
                msg = f"Error de automatización al acceder a {url}: {e}"
                logger.error(msg, exc=e)
                raise NetworkError(msg) from e
            finally:
                await browser.close()  # pyright: ignore[reportUnknownMemberType]
        content_hash = hashlib.sha256(html_content.encode("utf-8")).hexdigest()

        return Snapshot(
            fuente_id=fuente.id,
            fecha_captura=datetime.now(UTC),
            contenido_crudo=html_content,
            hash_contenido=content_hash,
            estado_ejecucion="SUCCESS",
        )

    async def extract(self, snapshot: Snapshot, fuente: Fuente, **kwargs: Any) -> list[dict[str, str | None]]:
        """
        Delega la extracción al motor de selectores CSS.
        Playwright se encarga del fetch (renderizado), pero para la extracción
        usamos selectolax sobre el snapshot capturado por eficiencia.
        """
        # Reutilizamos la lógica de HtmlStaticScraper pero asíncrona
        from src.infra.scraping.html_static import HtmlStaticScraper

        static_scraper = HtmlStaticScraper()
        return await static_scraper.extract(snapshot, fuente, **kwargs)
