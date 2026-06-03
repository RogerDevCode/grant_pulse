"""Cliente LLM para extracción estructurada de convocatorias financiables.

El objetivo no es "preguntar al modelo y confiar". El objetivo es:
- recortar el contexto a lo relevante,
- mantener el presupuesto de contexto alrededor de 100k caracteres,
- usar modelos free que existan hoy en OpenRouter,
- limitar la cadencia de requests para no pelear con rate limits,
- y fallar explícitamente cuando la respuesta no sea utilizable.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urljoin, urlparse

import httpx
from markdownify import markdownify as md
from selectolax.parser import HTMLParser

from src.core.domain.entities import SelectorConfig
from src.core.domain.exceptions import ExtractionError, ScrapingError
from src.infra.config import settings
from src.infra.logging import get_logger

logger = get_logger(__name__)

_SKIP_STATUS_CODES = {400, 404, 429, 502, 503, 529}
_NOISE_SELECTORS = (
    "script",
    "style",
    "nav",
    "footer",
    "iframe",
    "svg",
    "head",
    "noscript",
    "header",
    "aside",
    "form",
    ".cookie-banner",
    ".popup",
    ".modal",
    ".advertisement",
    ".ads",
)
_DEFAULT_FIELDS_SCHEMA: dict[str, str] = {
    "identificador": "ID único, slug o código del fondo. Si no existe, genera uno corto y estable.",
    "titulo": "Nombre completo de la convocatoria o fondo.",
    "descripcion": "Breve descripción del fondo. null si no aparece.",
    "url_detalle": "URL absoluta al detalle del fondo. Si es relativa, resolverla con la base.",
    "estado": "Uno de: ABIERTO, CERRADO, PROXIMAMENTE, ADJUDICADO.",
    "fecha_cierre": "Fecha de cierre en texto original. null si no aparece.",
    "monto": "Monto máximo o referencia de financiamiento. null si no aparece.",
}
_FIELD_ORDER = ("identificador", "titulo", "descripcion", "url_detalle", "estado", "fecha_cierre", "monto")
_CANDIDATE_LIST_KEYS = ("items", "convocatorias", "fondos", "results", "data", "concursos", "proyectos", "entries")


@runtime_checkable
class StructuredLLMClient(Protocol):
    """Contrato mínimo que consumen los scrapers LLM-aware."""

    provider_name: str
    max_content_chars: int
    max_output_tokens: int
    request_timeout_seconds: int

    async def chat_completion(self, prompt: str, system_prompt: str = ..., timeout: int | None = ...) -> str: ...

    async def extract_from_html(
        self,
        html_content: str,
        fields_schema: dict[str, str],
        base_url: str,
        institution_name: str = "",
        selectors: SelectorConfig | None = None,
        max_content_chars: int | None = None,
    ) -> list[dict[str, Any]]: ...

    async def discover_funding_url(self, html_content: str, base_url: str) -> str | None: ...


class _AsyncRateLimiter:
    """Limiter simple para espaciar requests LLM entre modelos y fuentes."""

    def __init__(self, min_interval_seconds: float) -> None:
        self._min_interval_seconds = min_interval_seconds
        self._lock = asyncio.Lock()
        self._last_request_monotonic = 0.0

    async def wait(self) -> float:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_monotonic
            sleep_seconds = self._min_interval_seconds - elapsed
            if sleep_seconds > 0:
                await asyncio.sleep(sleep_seconds)
            self._last_request_monotonic = time.monotonic()
            return max(sleep_seconds, 0.0)


_RATE_LIMITER = _AsyncRateLimiter(settings.LLM_MIN_SECONDS_BETWEEN_REQUESTS)


def _normalize_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _extract_attr_or_text(node: Any, selector: str) -> str | None:
    if selector.startswith("attr:"):
        attr_name = selector.split(":", 1)[1]
        attr_val = getattr(node, "attributes", {}).get(attr_name)
        if isinstance(attr_val, str):
            res_val: str = attr_val.strip()  # pyright: ignore[reportUnknownVariableType]
            return res_val or None
        return None

    text = node.text(strip=True) if hasattr(node, "text") else ""
    value = text.strip()
    return value or None


def _resolve_relative_url(raw_url: str, base_url: str) -> str:
    parsed = urlparse(raw_url)
    if parsed.scheme and parsed.netloc:
        return raw_url
    return urljoin(base_url.rstrip("/") + "/", raw_url.lstrip("/"))


def _payload_looks_like_item_collection(raw: Any) -> bool:
    if isinstance(raw, list):
        return True
    if isinstance(raw, dict):
        if any(key in raw for key in _CANDIDATE_LIST_KEYS):
            return True
        return any(isinstance(value, list) for value in raw.values())  # pyright: ignore[reportUnknownVariableType]
    return False


def _extract_json_from_text(text: str) -> Any:
    """Intenta recuperar JSON desde una respuesta que puede venir con ruido."""

    cleaned = text.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```json\s*([\s\S]+?)\s*```", cleaned)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    match = re.search(r"```\s*([\s\S]+?)\s*```", cleaned)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    first_object = cleaned.find("{")
    first_array = cleaned.find("[")
    candidates: list[tuple[int, str]] = []
    if first_object != -1:
        candidates.append((first_object, "{"))
    if first_array != -1:
        candidates.append((first_array, "["))
    candidates.sort(key=lambda item: item[0])

    for start, start_char in candidates:
        end_char = "}" if start_char == "{" else "]"
        end = cleaned.rfind(end_char)
        if end <= start:
            continue
        candidate = cleaned[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    return None


def _normalize_items(raw: Any) -> list[dict[str, Any]]:
    """Normaliza distintas formas de payload LLM a una lista de dicts."""

    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]  # pyright: ignore[reportUnknownVariableType]

    if isinstance(raw, dict):
        for key in _CANDIDATE_LIST_KEYS:
            value = raw.get(key)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]  # pyright: ignore[reportUnknownVariableType]

        for key, value in raw.items():  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType, reportUnknownArgumentType]
            if isinstance(value, list) and value and isinstance(value[0], dict):
                logger.info("Usando clave alternativa para lista de items", key=key)
                return [item for item in value if isinstance(item, dict)]  # pyright: ignore[reportUnknownVariableType]

    return []


def _summarize_item_node(
    node: Any,
    selectors: SelectorConfig | None,
    base_url: str,
    index: int,
) -> str:
    lines = [f"### Item {index + 1}"]

    if selectors is not None:
        field_to_selector = {
            "identificador": selectors.identificador,
            "titulo": selectors.titulo,
            "descripcion": selectors.descripcion,
            "estado": selectors.estado,
            "fecha_cierre": selectors.fecha_cierre,
            "monto": selectors.monto,
        }

        for field_name in _FIELD_ORDER:
            selector = field_to_selector.get(field_name)
            if not selector:
                continue

            if selector.startswith("attr:"):
                root = node
            else:
                root = node.css_first(selector) if hasattr(node, "css_first") else None
                if root is None:
                    continue

            value = _extract_attr_or_text(root, selector)
            if value:
                lines.append(f"- {field_name}: {value}")

        link_node = node.css_first(selectors.link_detalle) if hasattr(node, "css_first") else None
        if link_node is None and getattr(node, "tag", "") == "a":
            link_node = node
        href_val = getattr(link_node, "attributes", {}).get("href") if link_node else None
        if isinstance(href_val, str) and href_val.strip():
            lines.append(f"- url_detalle: {_resolve_relative_url(href_val.strip(), base_url)}")

    raw_html = getattr(node, "html", "") or ""
    snippet = md(raw_html, bullets="-", strip=["img"])
    snippet = _normalize_whitespace(snippet)
    if snippet:
        lines.append("")
        lines.append("Markdown del item:")
        lines.append(snippet[:4_000])

    return "\n".join(lines).strip()


def _build_markdown_context(
    html_content: str,
    base_url: str,
    selectors: SelectorConfig | None,
    max_chars: int,
) -> str:
    tree = HTMLParser(html_content)
    for tag in tree.css(", ".join(_NOISE_SELECTORS)):
        tag.decompose()

    fragments: list[str] = []
    if selectors is not None and selectors.contenedor_items:
        try:
            item_nodes = tree.css(selectors.contenedor_items)
        except Exception as exc:
            logger.warning(
                "No se pudieron resolver los selectores de contexto para LLM",
                selector=selectors.contenedor_items,
                exc=exc,
            )
            item_nodes = []

        for index, node in enumerate(item_nodes):
            fragment = _summarize_item_node(node, selectors, base_url, index)
            if not fragment:
                continue

            projected_size = len("\n\n---\n\n".join(fragments)) + len(fragment)
            if projected_size > max_chars:
                break
            fragments.append(fragment)

    if fragments:
        return _normalize_whitespace("\n\n---\n\n".join(fragments))

    body_html = tree.body.html if tree.body and tree.body.html is not None else html_content
    markdown_content = md(body_html, bullets="-", strip=["img"])
    markdown_content = _normalize_whitespace(markdown_content)
    if len(markdown_content) > max_chars:
        markdown_content = markdown_content[:max_chars]
    return markdown_content


def _default_extraction_prompt(fields_schema: dict[str, str]) -> str:
    schema_lines = "\n".join(f'  - "{field}": {description}' for field, description in fields_schema.items())
    return schema_lines


class OpenRouterClient:
    """Cliente OpenRouter con failover, backoff y parsing robusto."""

    provider_name = "openrouter"
    completion_tokens_key = "max_tokens"

    def __init__(self) -> None:
        self.api_key = settings.OPENROUTER_API_KEY or settings.LLM_API_KEY
        self.models = list(settings.LLM_MODELS_FALLBACK)
        self.max_content_chars = settings.LLM_MAX_CONTENT_CHARS
        self.max_output_tokens = settings.LLM_MAX_OUTPUT_TOKENS
        self.request_timeout_seconds = settings.LLM_REQUEST_TIMEOUT_SECONDS
        self._rate_limiter = _AsyncRateLimiter(settings.LLM_MIN_SECONDS_BETWEEN_REQUESTS)
        self._sleep = asyncio.sleep
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": settings.OPENROUTER_SITE_URL,
            "X-Title": "GrantPulse",
            "Content-Type": "application/json",
        }

    async def _respect_rate_limit(self) -> None:
        await self._rate_limiter.wait()

    async def chat_completion(
        self,
        prompt: str,
        system_prompt: str = "Eres un asistente experto en extracción de datos estructurados.",
        timeout: int | None = None,
    ) -> str:
        """Envia un prompt probando la cascada de modelos configurada."""

        if not self.api_key:
            logger.error("OPENROUTER_API_KEY no configurada. Motor LLM deshabilitado.")
            raise ScrapingError(
                "OPENROUTER_API_KEY no está configurada. Configura la variable de entorno para habilitar LLM."
            )

        headers = self._build_headers()
        effective_timeout = timeout or self.request_timeout_seconds
        last_error: str = "Sin errores registrados"

        for model_index, model_id in enumerate(self.models):
            if model_index > 0:
                await self._respect_rate_limit()

            payload: dict[str, Any] = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
                "top_p": 1.0,
                self.completion_tokens_key: self.max_output_tokens,
            }

            logger.info(
                "Intentando chat completion con LLM",
                provider=self.provider_name,
                model=model_id,
                prompt_chars=len(prompt),
            )

            try:
                async with httpx.AsyncClient(timeout=effective_timeout) as client:
                    response = await client.post(self.base_url, headers=headers, json=payload)
            except httpx.TimeoutException as exc:
                last_error = f"Timeout en {model_id}"
                logger.warning("Timeout con modelo LLM", provider=self.provider_name, model=model_id, exc=exc)
                continue
            except httpx.RequestError as exc:
                last_error = f"Error de red en {model_id}: {exc}"
                logger.warning("Error de red al invocar LLM", provider=self.provider_name, model=model_id, exc=exc)
                continue

            if response.status_code in _SKIP_STATUS_CODES:
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.warning(
                    "Modelo LLM no disponible o rechazado",
                    provider=self.provider_name,
                    model=model_id,
                    status=response.status_code,
                    preview=response.text[:200],
                )
                if response.status_code in {429, 503, 529}:
                    retry_after_raw = response.headers.get("Retry-After")
                    sleep_seconds = 0.0
                    if retry_after_raw:
                        try:
                            sleep_seconds = max(float(retry_after_raw), 0.0)
                        except ValueError:
                            sleep_seconds = 0.0
                    if sleep_seconds <= 0:
                        sleep_seconds = min(30.0, 2.0**model_index)
                    sleep_seconds += random.uniform(0.0, 0.75)
                    logger.info(
                        "Aplicando backoff por rate limit",
                        provider=self.provider_name,
                        model=model_id,
                        sleep_seconds=round(sleep_seconds, 2),
                    )
                    await self._sleep(sleep_seconds)
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                last_error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
                logger.warning(
                    "Error HTTP al invocar LLM",
                    provider=self.provider_name,
                    model=model_id,
                    status=exc.response.status_code,
                    preview=exc.response.text[:200],
                    exc=exc,
                )
                continue

            try:
                data = response.json()
            except ValueError as exc:
                last_error = f"Respuesta no JSON en {model_id}"
                logger.warning(
                    "Respuesta no JSON del LLM",
                    provider=self.provider_name,
                    model=model_id,
                    exc=exc,
                    preview=response.text[:200],
                )
                continue

            choices = data.get("choices", [])
            if not choices:
                last_error = f"Respuesta vacía de {model_id}: {data}"
                logger.warning("Respuesta sin choices", provider=self.provider_name, model=model_id)
                continue

            content = choices[0].get("message", {}).get("content", "")
            if not content:
                last_error = f"Content vacío de {model_id}"
                logger.warning("Content vacío del LLM", provider=self.provider_name, model=model_id)
                continue

            logger.info("LLM respondió exitosamente", provider=self.provider_name, model=model_id, chars=len(content))
            return str(content)

        msg = (
            f"FALLO_LLM_TOTAL: Ninguno de los {len(self.models)} modelos respondió correctamente. "
            f"Último error: {last_error}"
        )
        logger.error(msg)
        raise ScrapingError(msg)

    async def extract_from_html(
        self,
        html_content: str,
        fields_schema: dict[str, str],
        base_url: str,
        institution_name: str = "",
        selectors: SelectorConfig | None = None,
        max_content_chars: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Extrae convocatorias desde HTML crudo.

        El contexto se recorta antes de enviar al modelo y se priorizan los
        nodos de la lista, si existen.
        """

        effective_schema = fields_schema or _DEFAULT_FIELDS_SCHEMA
        budget = max_content_chars or self.max_content_chars
        markdown_content = _build_markdown_context(
            html_content=html_content,
            base_url=base_url,
            selectors=selectors,
            max_chars=budget,
        )

        if not markdown_content.strip():
            raise ExtractionError("No se pudo construir un contexto markdown utilizable para el LLM")

        original_chars = len(markdown_content)
        if original_chars > budget:
            logger.warning(
                "Contexto LLM truncado por presupuesto de caracteres",
                original_chars=original_chars,
                budget_chars=budget,
                base_url=base_url,
            )

        schema_str = _default_extraction_prompt(effective_schema)
        institution_suffix = f" del portal de {institution_name}" if institution_name else ""

        system_prompt = (
            "Eres un agente de extracción de datos estructurados especializado en convocatorias y financiamiento. "
            "Devuelves únicamente JSON válido, sin comentarios ni texto adicional."
        )
        prompt = (
            f"Analiza el siguiente documento Markdown extraído{institution_suffix} ({base_url}).\n\n"
            "OBJETIVO:\n"
            "Extrae todas las convocatorias, fondos o programas de financiamiento que estén listados en el contenido.\n\n"
            "ESQUEMA OBLIGATORIO POR ITEM:\n"
            f"{schema_str}\n\n"
            "REGLAS OBLIGATORIAS:\n"
            "1. Devuelve solo JSON válido.\n"
            "2. La raíz debe ser un objeto con la clave 'items'.\n"
            '3. Si no hay fondos o convocatorias, devuelve {"items": []}.\n'
            "4. No inventes fechas ni montos. Si no están escritos, usa null.\n"
            "5. No extraigas noticias, editoriales ni contenido decorativo.\n"
            "6. Prioriza convocatorias abiertas o activas. Si el estado no es claro, conserva el texto literal observado.\n"
            "7. URL relativa => URL absoluta usando la base del portal.\n"
            "8. No agregues texto fuera del JSON.\n\n"
            f"DOCUMENTO:\n{markdown_content}"
        )

        response_text = await self.chat_completion(
            prompt, system_prompt=system_prompt, timeout=self.request_timeout_seconds
        )
        parsed = _extract_json_from_text(response_text)
        if parsed is None:
            logger.error(
                "No se pudo extraer JSON válido de la respuesta LLM",
                preview=response_text[:300],
                base_url=base_url,
            )
            raise ExtractionError("La respuesta LLM no contiene JSON válido")

        items = _normalize_items(parsed)
        if not items and not _payload_looks_like_item_collection(parsed):
            logger.error(
                "La respuesta LLM no incluyó una colección de items reconocible",
                preview=response_text[:300],
                base_url=base_url,
            )
            raise ExtractionError("La respuesta LLM no siguió el contrato de items")

        logger.info(
            "LLM extrajo items",
            base_url=base_url,
            items=len(items),
            chars=original_chars,
        )
        return items

    async def discover_funding_url(self, html_content: str, base_url: str) -> str | None:
        """
        Descubre el link de la sección de financiamiento cuando no está explícito.

        Se mantiene como utilidad de frontera, no como flujo principal.
        """

        tree = HTMLParser(html_content)
        for tag in tree.css("script, style, iframe, svg, noscript"):
            tag.decompose()

        clean_html: str = tree.body.html if tree.body and tree.body.html is not None else html_content
        markdown_nav: str = _normalize_whitespace(md(clean_html, strip=["img"]))

        parsed_base = urlparse(base_url)
        domain = f"{parsed_base.scheme}://{parsed_base.netloc}"

        system_prompt = (
            "Eres un navegador web experto en portales de financiamiento chilenos. "
            "Identificas el link que conduce a la sección de convocatorias o fondos y respondes solo JSON."
        )
        prompt = (
            f"Página de inicio: {base_url}\n\n"
            "Busca en el contenido Markdown el link que lleva a 'Convocatorias', 'Fondos', "
            "'Concursos' o 'Financiamiento'.\n\n"
            "REGLAS:\n"
            '1. Devuelve solo este JSON: {"discovered_url": "URL_COMPLETA"}\n'
            f"2. Si el link es relativo, complétalo con la base {domain}\n"
            '3. Si no hay link claro, devuelve {"discovered_url": null}\n\n'
            f"CONTENIDO:\n{markdown_nav[:40_000]}"
        )

        try:
            response_text = await self.chat_completion(prompt, system_prompt=system_prompt, timeout=45)
        except ScrapingError as exc:
            logger.warning("Discovery LLM falló", base_url=base_url, exc=exc)
            return None

        parsed = _extract_json_from_text(response_text)
        if not isinstance(parsed, dict):
            logger.warning("Discovery LLM no devolvió un dict JSON válido", preview=response_text[:200])
            return None

        discovered = parsed.get("discovered_url")  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
        if not discovered or not isinstance(discovered, str):
            return None

        discovered = discovered.strip()
        parsed_url = urlparse(discovered)
        if not parsed_url.scheme:
            discovered = urljoin(domain + "/", discovered.lstrip("/"))
            parsed_url = urlparse(discovered)

        if not parsed_url.netloc:
            logger.warning("Discovery LLM devolvió una URL inválida", url=discovered)
            return None

        logger.info("URL de financiamiento descubierta por LLM", url=discovered, base=base_url)
        return discovered


class GroqClient(OpenRouterClient):
    """Cliente Groq sobre el endpoint OpenAI-compatible oficial."""

    provider_name = "groq"
    completion_tokens_key = "max_completion_tokens"

    def __init__(self) -> None:
        self.api_key = settings.GROQ_API_KEY
        self.models = list(settings.GROQ_MODELS_FALLBACK)
        self.max_content_chars = settings.GROQ_MAX_CONTENT_CHARS
        self.max_output_tokens = settings.GROQ_MAX_OUTPUT_TOKENS
        self.request_timeout_seconds = settings.GROQ_REQUEST_TIMEOUT_SECONDS
        self._rate_limiter = _AsyncRateLimiter(settings.GROQ_MIN_SECONDS_BETWEEN_REQUESTS)
        self._sleep = asyncio.sleep
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "GrantPulse",
        }


class NvidiaClient(OpenRouterClient):
    """Cliente NVIDIA Integrate para modelos de alta capacidad como GLM-5.1."""

    provider_name = "nvidia"
    completion_tokens_key = "max_tokens"

    def __init__(self) -> None:
        self.api_key = settings.NVIDIA_API_KEY
        self.models = [settings.NVIDIA_MODEL]
        self.max_content_chars = settings.LLM_MAX_CONTENT_CHARS
        self.max_output_tokens = settings.LLM_MAX_OUTPUT_TOKENS
        self.request_timeout_seconds = settings.LLM_REQUEST_TIMEOUT_SECONDS
        self._rate_limiter = _AsyncRateLimiter(settings.LLM_MIN_SECONDS_BETWEEN_REQUESTS)
        self._sleep = asyncio.sleep
        self.base_url = settings.NVIDIA_BASE_URL

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }


def build_llm_client(preferred_provider: str | None = None) -> StructuredLLMClient:
    """Factory explícita para elegir proveedor LLM sin acoplar la capa de scraping."""

    provider = (preferred_provider or settings.LLM_PROVIDER).strip().lower()

    if provider == "nvidia":
        return NvidiaClient()
    if provider == "groq":
        return GroqClient()
    if provider == "openrouter":
        return OpenRouterClient()

    # auto: priorizamos NVIDIA si existe API key, luego Groq, luego OpenRouter.
    if settings.NVIDIA_API_KEY:
        return NvidiaClient()
    if settings.GROQ_API_KEY:
        return GroqClient()
    if settings.OPENROUTER_API_KEY or settings.LLM_API_KEY:
        return OpenRouterClient()

    # Fail-fast controlado: devolvemos el cliente preferido por defecto para que
    # el caller obtenga el error de configuración en el primer request real.
    logger.warning("No hay API key configurada para LLMs; se usará OpenRouter por defecto")
    return OpenRouterClient()
