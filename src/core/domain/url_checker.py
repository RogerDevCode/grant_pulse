import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
from src.infra.logging import get_logger

logger = get_logger(__name__)

class UrlChecker:
    @classmethod
    async def check_url(cls, url: str) -> str:
        """
        Verifica si una URL está disponible usando Playwright.
        Retorna:
        - "VALID" si la página carga correctamente (HTTP 2xx, 3xx y termina bien)
        - "PERMANENT_GONE" si es un error 404, 410 o la página indica que ya no existe.
        - "TRANSIENT_ERROR" si hay timeout, error de red o bloqueos temporales.
        """
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                # Crear contexto limpio sin cookies ni estado residual
                context = await browser.new_context(
                    ignore_https_errors=True,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                
                try:
                    # Usamos un timeout corto (15 segundos) ya que solo queremos comprobar vigencia
                    response = await page.goto(url, timeout=15000, wait_until="domcontentloaded")
                    
                    if not response:
                        return "TRANSIENT_ERROR"
                        
                    status = response.status
                    
                    if status in (404, 410):
                        return "PERMANENT_GONE"
                    
                    if status >= 500 or status in (403, 405, 429):
                        # Asumimos WAF o error temporal de servidor
                        return "TRANSIENT_ERROR"
                        
                    if 200 <= status < 400:
                        return "VALID"
                        
                    return "TRANSIENT_ERROR"
                    
                except PlaywrightTimeoutError:
                    logger.warning("Timeout al verificar URL con Playwright", url=url)
                    return "TRANSIENT_ERROR"
                except PlaywrightError as e:
                    logger.warning("Error de Playwright al verificar URL", url=url, error=str(e))
                    return "TRANSIENT_ERROR"
                finally:
                    await context.close()
                    await browser.close()
                    
        except Exception as e:
            logger.error("Error inesperado en UrlChecker", url=url, exc=e)
            return "TRANSIENT_ERROR"
