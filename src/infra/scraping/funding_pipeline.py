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

from src.core.application.run_context import get_run_id
from src.core.domain.entities import Fuente, Snapshot
from src.core.domain.exceptions import ExtractionError, NetworkError, ScrapingError
from src.core.domain.ports import ScraperPort
from src.infra.logging import get_logger
from src.infra.scraping.curl_cffi import CurlCffiScraper
from src.infra.scraping.fosis_multipage import FosisMultiPageScraper
from src.infra.scraping.html_static import HtmlStaticScraper
from src.infra.scraping.json_api import JsonApiScraper
from src.infra.scraping.rss_feed import RssFeedScraper
from src.infra.scraping.subdere_homepage import SubdereHomepageScraper
from src.infra.scraping.trafilatura_scraper import TrafilaturaScraper
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
        browser: ScraperPort | None = None,  # noqa: ARG002
        llm: ScraperPort | None = None,  # noqa: ARG002
        wp_ajax: ScraperPort | None = None,
        rss_feed: ScraperPort | None = None,
        curl_cffi: ScraperPort | None = None,
        subdere_homepage: ScraperPort | None = None,
        fosis_multipage: ScraperPort | None = None,
        trafilatura: ScraperPort | None = None,
        sleep_fn: Any = asyncio.sleep,
    ) -> None:
        self._profile = profile
        self._html_static = html_static or HtmlStaticScraper()
        self._json_api = json_api or JsonApiScraper()
        self._browser: ScraperPort | None = None  # lazy — solo si se usa estrategia browser
        self._llm: ScraperPort | None = None  # lazy — solo si se usa estrategia llm
        self._wp_ajax = wp_ajax or WpAjaxScraper()
        self._rss_feed = rss_feed or RssFeedScraper()
        self._curl_cffi = curl_cffi or CurlCffiScraper()
        self._subdere_homepage = subdere_homepage or SubdereHomepageScraper()
        self._fosis_multipage = fosis_multipage or FosisMultiPageScraper()
        self._trafilatura = trafilatura or TrafilaturaScraper()
        self._sleep = sleep_fn
        self._metrics = PipelineMetrics(step_metrics=[])
        self._state: _AttemptState | None = None

    def _clone_fuente(self, fuente: Fuente, url: str) -> Fuente:
        from pydantic import HttpUrl, TypeAdapter

        url_obj = TypeAdapter(HttpUrl).validate_python(url)
        nueva_config = fuente.configuracion_reglas.model_copy(update={"url_busqueda": url_obj})
        return fuente.model_copy(update={"configuracion_reglas": nueva_config})

    async def _fetch_with_kind(self, kind: str, fuente: Fuente) -> Snapshot:
        if kind == "html_static":
            return await self._html_static.fetch(fuente)
        if kind == "json_api":
            return await self._json_api.fetch(fuente)
        if kind == "browser":
            if self._browser is None:
                from src.infra.scraping.browser import PlaywrightScraper

                self._browser = PlaywrightScraper()
            return await self._browser.fetch(fuente)
        if kind == "llm":
            if self._llm is None:
                from src.infra.scraping.llm_scraper import LlmScraper

                self._llm = LlmScraper()
            return await self._llm.fetch(fuente)
        if kind == "curl_cffi":
            return await self._curl_cffi.fetch(fuente)
        if kind == "wp_ajax":
            return await self._wp_ajax.fetch(fuente)
        if kind == "rss_feed":
            return await self._rss_feed.fetch(fuente)
        if kind == "subdere_homepage":
            return await self._subdere_homepage.fetch(fuente)
        if kind == "fosis_multipage":
            return await self._fosis_multipage.fetch(fuente)
        raise ScrapingError(f"Fetch kind no soportado: {kind}")

    def _fusionar_resultados(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fusión inteligente probabilística (Fuzzy Linkage) usando Jaro-Winkler y Confidence Scores."""
        import jellyfish

        # Agrupar items por coincidencia
        grupos: list[list[dict[str, Any]]] = []

        for item in items:
            ident = item.get("identificador")
            tit = str(item.get("titulo", "")).lower().strip()

            # Buscar si pertenece a un grupo existente
            grupo_encontrado = None
            for idx, grupo in enumerate(grupos):
                for miembro in grupo:
                    m_ident = miembro.get("identificador")
                    m_tit = str(miembro.get("titulo", "")).lower().strip()

                    # Regla 1: Identificador exacto (y válido)
                    if ident and m_ident and ident != "TRAF-AUTO" and m_ident != "TRAF-AUTO" and ident == m_ident:
                        grupo_encontrado = idx
                        break

                    # Regla 2: Fuzzy matching en título (Jaro-Winkler > 0.85)
                    if tit and m_tit:
                        similitud = jellyfish.jaro_winkler_similarity(tit, m_tit)
                        if similitud > 0.85:
                            grupo_encontrado = idx
                            break
                if grupo_encontrado is not None:
                    break

            if grupo_encontrado is not None:
                grupos[grupo_encontrado].append(item)
            else:
                grupos.append([item])

        fusionados: list[dict[str, Any]] = []
        for grupo in grupos:
            # Ordenar el grupo por _confidence_score descendente
            grupo_ordenado = sorted(grupo, key=lambda x: x.get("_confidence_score", 0.0), reverse=True)

            # El item base es el de mayor confianza
            item_base = dict(grupo_ordenado[0])

            # Completar campos nulos usando los de menor confianza
            for miembro in grupo_ordenado[1:]:
                for key, value in miembro.items():
                    if key == "_confidence_score":
                        continue
                    if not item_base.get(key) and value:
                        item_base[key] = value

            # Limpiar clave interna
            item_base.pop("_confidence_score", None)
            fusionados.append(item_base)

        return fusionados

    async def _extract_with_kind(
        self,
        kind: str,
        snapshot: Snapshot,
        fuente: Fuente,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        if kind == "html_static":
            # Fase 1: Extracción Paralela (ParScrape) - Determinista + Heurística en el mismo snapshot
            logger.info("Extrayendo concurrentemente vía [html_static, trafilatura]", fuente=fuente.nombre)
            res = await asyncio.gather(
                self._html_static.extract(snapshot, fuente, **kwargs),
                self._trafilatura.extract(snapshot, fuente, **kwargs),
                return_exceptions=True
            )
            res_html: Any = res[0]
            res_traf: Any = res[1]

            items: list[dict[str, Any]] = []
            if isinstance(res_html, list):
                # Type cast manual para Mypy ya que gather retorna Any
                for i in res_html:
                    if isinstance(i, dict):
                        i["_confidence_score"] = 0.9  # CSS Selector (alto)
                        items.append(i)
            else:
                logger.warning("Fallo en extractor html_static", fuente=fuente.nombre, exc=res_html)

            if isinstance(res_traf, list):
                for i in res_traf:
                    if isinstance(i, dict):
                        i["_confidence_score"] = 0.6  # Trafilatura (medio)
                        items.append(i)
            else:
                logger.warning("Fallo en extractor trafilatura", fuente=fuente.nombre, exc=res_traf)

            return self._fusionar_resultados(items)
        if kind == "json_api":
            return await self._json_api.extract(snapshot, fuente, **kwargs)
        if kind == "llm":
            if self._llm is None:
                from src.infra.scraping.llm_scraper import LlmScraper

                self._llm = LlmScraper()
            budget = kwargs.get("max_content_chars") or self._profile.max_llm_context_chars
            return await self._llm.extract(snapshot, fuente, max_content_chars=budget)
        if kind == "wp_ajax":
            return await self._wp_ajax.extract(snapshot, fuente, **kwargs)
        if kind == "rss_feed":
            return await self._rss_feed.extract(snapshot, fuente, **kwargs)
        if kind == "curl_cffi":
            return await self._curl_cffi.extract(snapshot, fuente, **kwargs)
        if kind == "subdere_homepage":
            return await self._subdere_homepage.extract(snapshot, fuente, **kwargs)
        if kind == "fosis_multipage":
            return await self._fosis_multipage.extract(snapshot, fuente, **kwargs)
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
        logger.error(msg, fuente=fuente.nombre, profile=self._profile.key, exc=last_error, run_id=get_run_id())
        if isinstance(last_error, NetworkError):
            raise last_error
        raise NetworkError(msg) from last_error

    async def extract(self, snapshot: Snapshot, fuente: Fuente, **kwargs: Any) -> list[dict[str, Any]]:
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

                # --- AUTO-HEALING ---
                if step.extractor == "html_static" and not resultados:
                    logger.info("Intentando auto-healing de selectores con LLM", fuente=fuente.nombre)
                    from src.infra.llm.client import build_llm_client

                    llm_client = build_llm_client()
                    healed = await llm_client.heal_selectors(
                        current_snapshot.contenido_crudo,
                        fuente.nombre,
                        str(fuente.url_base),
                    )
                    if healed:
                        logger.info("Selectores sanados, reintentando extracción", fuente=fuente.nombre)
                        from pydantic import ValidationError

                        try:
                            if fuente.configuracion_reglas.selectores:
                                healed_selectors = fuente.configuracion_reglas.selectores.model_copy(update=healed)
                            else:
                                from src.core.domain.entities import SelectorConfig

                                healed_selectors = SelectorConfig(**healed)
                            healed_rules = fuente.configuracion_reglas.model_copy(update={"selectores": healed_selectors})
                            healed_fuente = fuente.model_copy(update={"configuracion_reglas": healed_rules})

                            resultados = await self._html_static.extract(current_snapshot, healed_fuente, **kwargs)
                            if resultados:
                                logger.info("Auto-healing exitoso", fuente=fuente.nombre, items=len(resultados))

                                # Auto-guardar los selectores sanados en el YAML de la fuente
                                from src.infra.rules_loader import update_selectors_in_yaml
                                try:
                                    update_selectors_in_yaml(fuente.nombre, healed)
                                except Exception as save_exc:
                                    logger.warning("No se pudo auto-guardar el YAML con selectores sanados", exc=save_exc)

                                return resultados
                        except ValidationError as ve:
                            logger.warning("Auto-healing devolvió selectores inválidos, omitiendo", fuente=fuente.nombre, exc=ve)

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
        from src.infra.scraping.browser import PlaywrightScraper

        return PlaywrightScraper()
    if estrategia == "llm":
        from src.infra.scraping.llm_scraper import LlmScraper

        return LlmScraper()
    if estrategia == "wp_ajax":
        return WpAjaxScraper()
    if estrategia == "rss_feed":
        return RssFeedScraper()
    if estrategia == "curl_cffi":
        return CurlCffiScraper()
    if estrategia == "subdere_homepage":
        return SubdereHomepageScraper()
    if estrategia == "fosis_multipage":
        return FosisMultiPageScraper()
    return HtmlStaticScraper(timeout=15)


def source_profile_for_name(source_name: str) -> SourceProfile | None:
    return resolve_source_profile(source_name)
