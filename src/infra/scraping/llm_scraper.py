"""
Adaptador de scraping que utiliza LLMs para extraer datos de forma inteligente.

Este scraper actúa en dos fases:
  1. fetch(): Descarga el HTML con headers realistas (User-Agent de navegador).
  2. extract(): Delega la extracción al OpenRouterClient con contexto de institución.

Es el motor de extracción de último recurso cuando los selectores CSS fallan,
o el motor principal para fuentes cuya estructura HTML es demasiado dinámica.
"""

import hashlib
from datetime import UTC, datetime
from typing import Any

import httpx

from src.core.domain.entities import Fuente, Snapshot
from src.core.domain.exceptions import ExtractionError, NetworkError
from src.core.domain.ports import ScraperPort
from src.infra.llm.client import StructuredLLMClient, build_llm_client
from src.infra.logging import get_logger

logger = get_logger(__name__)

_REALISTIC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
}

# Esquema de campos que se le pide al LLM que extraiga
_FIELDS_SCHEMA: dict[str, str] = {
    "identificador": "ID único, slug o código del fondo. Si no existe, genera uno con las primeras 4 palabras del título.",
    "titulo": "Nombre completo de la convocatoria o fondo.",
    "descripcion": "Breve descripción del fondo (1-3 oraciones). null si no hay.",
    "url_detalle": "URL completa al detalle del fondo. Resolver relativas con la URL base.",
    "estado": "Estado del fondo: ABIERTO, CERRADO o PROXIMAMENTE.",
    "fecha_cierre": "Fecha de cierre de postulación en texto original del portal. null si no aparece.",
    "monto": "Monto máximo de financiamiento con su unidad (ej: '$10.000.000 CLP'). null si no aparece.",
}


class LlmScraper(ScraperPort):
    """
    Adaptador de scraping 'inteligente' basado en LLMs via OpenRouter.

    - fetch(): Descarga el HTML con User-Agent real y sigue redirecciones.
    - extract(): Usa OpenRouterClient con cascada de modelos para extraer items.
    """

    def __init__(self, timeout: int = 30, llm_client: StructuredLLMClient | None = None) -> None:
        self._timeout = timeout
        self.llm_client = llm_client or build_llm_client()

    async def fetch(self, fuente: Fuente) -> Snapshot:
        url = str(fuente.configuracion_reglas.url_busqueda)
        logger.info("LlmScraper: realizando fetch", url=url, fuente=fuente.nombre)

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                headers=_REALISTIC_HEADERS,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                html_content = response.text

        except httpx.HTTPStatusError as e:
            msg = f"Error HTTP {e.response.status_code} en fetch LLM para {url}"
            logger.error(msg, exc=e)
            raise NetworkError(msg) from e
        except httpx.RequestError as e:
            msg = f"Error de red en fetch LLM para {url}: {e}"
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
        Extrae items de convocatoria delegando al LLM con contexto institucional completo.

        El LLM recibe:
        - El nombre de la institución para contextualizar la búsqueda.
        - La URL base para resolver links relativos.
        - El esquema de campos exacto que debe devolver.
        - El HTML convertido a Markdown limpio y compacto.
        """
        logger.info(
            "LlmScraper: iniciando extracción con LLM",
            provider=self.llm_client.provider_name,
            fuente=fuente.nombre,
            fuente_id=str(fuente.id),
        )

        base_url = str(fuente.url_base)
        max_content_chars = kwargs.get("max_content_chars") or self.llm_client.max_content_chars

        try:
            raw_items = await self.llm_client.extract_from_html(
                html_content=snapshot.contenido_crudo,
                fields_schema=_FIELDS_SCHEMA,
                base_url=base_url,
                institution_name=fuente.nombre,
                selectors=fuente.configuracion_reglas.selectores,
                max_content_chars=max_content_chars,
            )
        except Exception as e:
            msg = f"Error en extracción LLM para fuente {fuente.nombre}: {e}"
            logger.error(msg, exc=e)
            raise ExtractionError(msg) from e

        if not raw_items:
            logger.warning(
                "LlmScraper: el LLM no encontró items en la página",
                provider=self.llm_client.provider_name,
                url=base_url,
                fuente=fuente.nombre,
            )
            return []

        # Normalizar tipos: todos los valores deben ser str | None para el pipeline
        normalized: list[dict[str, str | None]] = []
        for item in raw_items:
            row: dict[str, str | None] = {}
            for key in _FIELDS_SCHEMA:
                val = item.get(key)
                row[key] = str(val).strip() if val is not None and str(val).strip() else None
            normalized.append(row)

        logger.info(
            "LlmScraper: extracción completada",
            provider=self.llm_client.provider_name,
            items_encontrados=len(normalized),
            fuente=fuente.nombre,
        )
        return normalized
