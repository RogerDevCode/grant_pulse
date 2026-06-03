"""Pipeline compuesto por institución para recuperación orgánica, estática, browser y LLM.

Jerarquía de scraping:
1. API/Feed orgánico (REST API, RSS, AJAX) → SERCOTEC, FIA, ANID, CORFO
2. HTML estático (httpx + selectolax) → INDAP, ProChile, FOSIS, SUBDERE
3. Browser automation (Playwright) → solo como fallback
4. LLM → solo como último recurso
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Any

from src.core.domain.entities import Fuente, Snapshot
from src.core.domain.exceptions import ExtractionError, NetworkError, ScrapingError
from src.core.domain.ports import ScraperPort
from src.infra.logging import get_logger
from src.infra.scraping.browser import PlaywrightScraper
from src.infra.scraping.curl_cffi import CurlCffiScraper
from src.infra.scraping.html_static import HtmlStaticScraper
from src.infra.scraping.json_api import JsonApiScraper
from src.infra.scraping.llm_scraper import LlmScraper
from src.infra.scraping.rss_feed import RssFeedScraper
from src.infra.scraping.wp_ajax import WpAjaxScraper
from src.infra.sources.catalog import SourceProfile, resolve_source_profile

logger = get_logger(__name__)


@dataclass(slots=True)
class _AttemptState:
    step_index: int
    snapshot: Snapshot


@dataclass(slots=True)
class PipelineMetrics:
    step_metrics: list[dict[str, Any]]
    total_items: int = 0
    final_status: str = "PENDING"
    execution_time_seconds: float = 0.0


class CompositeFundingScraper(ScraperPort):
    """
    Scraper compuesto con DI explícita y registro de métricas.
    Orquesta la cascada: orgánico → estático → browser → LLM.
    """

    def __init__(
        self,
        profile: SourceProfile,
        html_static: ScraperPort | None = None,
        json_api: ScraperPort | None = None,
        browser: ScraperPort | None = None,
        llm: ScraperPort | None = None,
        wp_ajax: ScraperPort | None = None,
        rss_feed: ScraperPort | None = None,
        curl_cffi: ScraperPort | None = None,
        sleep_fn: Any = asyncio.sleep,
    ) -> None:
        self._profile = profile
        self._html_static = html_static or HtmlStaticScraper()
        self._json_api = json_api or JsonApiScraper()
        self._browser = browser or PlaywrightScraper()
        self._llm = llm or LlmScraper()
        self._wp_ajax = wp_ajax or WpAjaxScraper()
        self._rss_feed = rss_feed or RssFeedScraper()
        self._curl_cffi = curl_cffi or CurlCffiScraper()
        self._sleep = sleep_fn
        self._metrics = PipelineMetrics(step_metrics=[])
        self._state: _AttemptState | None = None

    def _clone_fuente(self, fuente: Fuente, url: str) -> Fuente:
        nueva_config = fuente.configuracion_reglas.model_copy(update={"url_busqueda": url})
        return fuente.model_copy(update={"configuracion_reglas": nueva_config})

    async def _fetch_with_kind(self, kind: str, fuente: Fuente) -> Snapshot:
        if kind == "html_static":
            return await self._html_static.fetch(fuente)
        if kind == "json_api":
            return await self._json_api.fetch(fuente)
        if kind == "browser":
            return await self._browser.fetch(fuente)
        if kind == "llm":
            return await self._llm.fetch(fuente)
        if kind == "corfo_especializado":
            from src.infra.scraping.corfo import CorfoScraper

            specialized = CorfoScraper()
            return await specialized.fetch(fuente)
        if kind == "resilient":
            from src.infra.scraping.resilient import ResilientFetcher

            resilient = ResilientFetcher()
            return await resilient.fetch(fuente)
        if kind == "curl_cffi":
            return await self._curl_cffi.fetch(fuente)
        if kind == "wp_ajax":
            return await self._wp_ajax.fetch(fuente)
        if kind == "rss_feed":
            return await self._rss_feed.fetch(fuente)
        raise ScrapingError(f"Fetch kind no soportado: {kind}")

    async def _extract_with_kind(
        self,
        kind: str,
        snapshot: Snapshot,
        fuente: Fuente,
        **kwargs: Any,
    ) -> list[dict[str, str | None]]:
        if kind == "html_static":
            return await self._html_static.extract(snapshot, fuente, **kwargs)
        if kind == "json_api":
            return await self._json_api.extract(snapshot, fuente, **kwargs)
        if kind == "llm":
            budget = kwargs.get("max_content_chars") or self._profile.max_llm_context_chars
            return await self._llm.extract(snapshot, fuente, max_content_chars=budget)
        if kind == "wp_ajax":
            return await self._wp_ajax.extract(snapshot, fuente, **kwargs)
        if kind == "rss_feed":
            return await self._rss_feed.extract(snapshot, fuente, **kwargs)
        if kind == "curl_cffi":
            return await self._curl_cffi.extract(snapshot, fuente, **kwargs)
        raise ScrapingError(f"Extract kind no soportado: {kind}")

    def _explicit_empty(self, content: str) -> bool:
        normalized = content.lower()
        return any(marker.lower() in normalized for marker in self._profile.empty_state_markers)

    async def _polite_pause(self, step_index: int, reason: str) -> None:
        if step_index <= 0:
            return

        sleep_seconds = self._profile.min_request_interval_seconds + random.uniform(0.1, 1.5)
        logger.info(
            "Pausa polida entre requests",
            fuente=self._profile.key,
            step_index=step_index,
            reason=reason,
            sleep_seconds=round(sleep_seconds, 2),
        )
        await self._sleep(sleep_seconds)

    async def fetch(self, fuente: Fuente) -> Snapshot:
        """Ejecuta el primer fetch exitoso del pipeline."""
        start_time = time.monotonic()
        last_error: Exception | None = None

        for index, step in enumerate(self._profile.steps):
            step_fuente = self._clone_fuente(fuente, step.url)
            if index > 0:
                await self._polite_pause(index, "fallback-fetch")

            step_start = time.monotonic()
            try:
                snapshot = await self._fetch_with_kind(step.fetcher, step_fuente)
                self._state = _AttemptState(step_index=index, snapshot=snapshot)

                self._metrics.step_metrics.append(
                    {
                        "step": index,
                        "fetcher": step.fetcher,
                        "status": "SUCCESS",
                        "latency": time.monotonic() - step_start,
                    }
                )
                return snapshot
            except Exception as exc:
                last_error = exc
                self._metrics.step_metrics.append(
                    {
                        "step": index,
                        "fetcher": step.fetcher,
                        "status": "FAILED",
                        "error": str(exc),
                        "latency": time.monotonic() - step_start,
                    }
                )
                logger.warning(
                    "Paso de fetch falló",
                    fuente=fuente.nombre,
                    fetcher=step.fetcher,
                    url=step.url,
                    exc=exc,
                )

        self._metrics.final_status = "FETCH_FAILED"
        self._metrics.execution_time_seconds = time.monotonic() - start_time
        msg = f"No se pudo obtener ningún snapshot para {fuente.nombre} usando el perfil {self._profile.key}"
        logger.error(msg, fuente=fuente.nombre, profile=self._profile.key, exc=last_error)
        if isinstance(last_error, NetworkError):
            raise last_error
        raise NetworkError(msg) from last_error

    async def extract(self, snapshot: Snapshot, fuente: Fuente, **kwargs: Any) -> list[dict[str, str | None]]:
        """Extrae items usando la cadena de mando del perfil."""
        if self._state is None:
            start_index = 0
        else:
            start_index = self._state.step_index if self._state.snapshot.id == snapshot.id else 0

        start_time = time.monotonic()
        last_error: Exception | None = None

        for index in range(start_index, len(self._profile.steps)):
            step = self._profile.steps[index]
            step_fuente = self._clone_fuente(fuente, step.url)
            current_snapshot = snapshot

            if index != start_index:
                await self._polite_pause(index, "fallback-extract")
                try:
                    current_snapshot = await self._fetch_with_kind(step.fetcher, step_fuente)
                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "Paso de fallback falló al fetch",
                        fuente=fuente.nombre,
                        profile=self._profile.key,
                        step_index=index,
                        fetcher=step.fetcher,
                        url=step.url,
                    )
                    continue

            try:
                resultados = await self._extract_with_kind(step.extractor, current_snapshot, step_fuente, **kwargs)
                if resultados:
                    self._state = _AttemptState(step_index=index, snapshot=current_snapshot)
                    self._metrics.total_items = len(resultados)
                    self._metrics.final_status = "SUCCESS"
                    self._metrics.execution_time_seconds = time.monotonic() - start_time

                    logger.info(
                        "Extracción exitosa con pipeline institucional",
                        fuente=fuente.nombre,
                        profile=self._profile.key,
                        step_index=index,
                        items=len(resultados),
                    )
                    return resultados

                if self._explicit_empty(current_snapshot.contenido_crudo):
                    self._metrics.total_items = 0
                    self._metrics.final_status = "SUCCESS_EMPTY"
                    self._metrics.execution_time_seconds = time.monotonic() - start_time
                    logger.info(
                        "Página vacía de forma explícita",
                        fuente=fuente.nombre,
                        profile=self._profile.key,
                        step_index=index,
                    )
                    return []

                logger.warning(
                    "Extracción vacía, probando siguiente fallback",
                    fuente=fuente.nombre,
                    profile=self._profile.key,
                    step_index=index,
                    extractor=step.extractor,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Paso de fallback falló al extraer",
                    fuente=fuente.nombre,
                    profile=self._profile.key,
                    step_index=index,
                    extractor=step.extractor,
                    url=step.url,
                    exc=exc,
                )
                continue

        self._metrics.final_status = "EXTRACTION_FAILED"
        self._metrics.execution_time_seconds = time.monotonic() - start_time
        msg = f"No se pudieron extraer datos de {fuente.nombre} tras agotar el pipeline"
        logger.error(msg, fuente=fuente.nombre, profile=self._profile.key, exc=last_error)
        raise ExtractionError(msg) from last_error


def build_scraper_for_source(fuente: Fuente, fallback_strategy: str | None = None) -> ScraperPort:
    """
    Factory de scrapers.

    Si la fuente está en el registry duro, usa el pipeline compuesto.
    En caso contrario, permite caer a la estrategia declarada en YAML.
    """

    profile = resolve_source_profile(fuente.nombre)
    if profile is not None:
        return CompositeFundingScraper(profile)

    estrategia = fallback_strategy or fuente.configuracion_reglas.estrategia
    if estrategia == "json_api":
        return JsonApiScraper()
    if estrategia == "browser":
        return PlaywrightScraper()
    if estrategia == "llm":
        return LlmScraper()
    if estrategia == "wp_ajax":
        return WpAjaxScraper()
    if estrategia == "rss_feed":
        return RssFeedScraper()
    if estrategia == "curl_cffi":
        return CurlCffiScraper()
    return HtmlStaticScraper(timeout=15)


def source_profile_for_name(source_name: str) -> SourceProfile | None:
    return resolve_source_profile(source_name)
