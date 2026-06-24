"""Servicio para verificar la disponibilidad de URLs en background."""

from typing import Literal

import httpx

from src.infra.logging import get_logger

logger = get_logger(__name__)

UrlStatus = Literal["VALID", "TRANSIENT_ERROR", "PERMANENT_GONE"]

class UrlChecker:
    """Ejecuta verificaciones HEAD/GET para determinar si una URL está disponible."""

    @staticmethod
    async def check_url(url: str) -> UrlStatus:
        if not url:
            return "PERMANENT_GONE"

        try:
            # Polite check with short timeout
            async with httpx.AsyncClient(timeout=3.0, verify=False, follow_redirects=True) as client:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                resp = await client.head(url, headers=headers)

                if resp.status_code >= 400:
                    if resp.status_code in (403, 404, 405, 410):
                        resp_get = await client.get(url, headers=headers)
                        if resp_get.status_code in (404, 410):
                            return "PERMANENT_GONE"
                        if resp_get.status_code >= 400:
                            return "TRANSIENT_ERROR"
                    elif resp.status_code in (404, 410):
                        return "PERMANENT_GONE"
                    else:
                        return "TRANSIENT_ERROR"

            return "VALID"
        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.debug(f"Error de red transitorio al chequear URL {url}: {str(e)}")
            return "TRANSIENT_ERROR"
        except Exception as e:
            logger.debug(f"Error inesperado al chequear URL {url}: {str(e)}")
            return "TRANSIENT_ERROR"
