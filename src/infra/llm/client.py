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
    "titulo": "Nombre completo de la convocatoria o fondo de financiamiento.",
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
        screenshot_b64: str | None = None,
    ) -> list[dict[str, Any]]: ...

    async def extract_single_detail(
        self,
        html_content: str,
        base_url: str,
        institution_name: str = "",
        max_content_chars: int | None = None,
    ) -> dict[str, Any] | None: ...

    async def discover_funding_url(self, html_content: str, base_url: str) -> str | None: ...

    async def heal_selectors(
        self,
        html_content: str,
        institution_name: str,
        base_url: str,
    ) -> dict[str, str] | None: ...


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
        prompt: str | list[dict[str, Any]],
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

        # Si el prompt es string, lo envolvemos. Si es multimodal (list), se usa directo.
        content = prompt if isinstance(prompt, list) else prompt

        for model_index, model_id in enumerate(self.models):
            if model_index > 0:
                await self._respect_rate_limit()

            payload: dict[str, Any] = {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
                "temperature": 0.0,
                "top_p": 1.0,
                self.completion_tokens_key: self.max_output_tokens,
            }

            logger.info(
                "Intentando chat completion con LLM",
                provider=self.provider_name,
                model=model_id,
                is_multimodal=isinstance(prompt, list),
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
        screenshot_b64: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Extrae convocatorias desde HTML crudo y/o captura de pantalla.
        """

        effective_schema = fields_schema or _DEFAULT_FIELDS_SCHEMA
        budget = max_content_chars or self.max_content_chars
        markdown_content = _build_markdown_context(
            html_content=html_content,
            base_url=base_url,
            selectors=selectors,
            max_chars=budget,
        )

        if not markdown_content.strip() and not screenshot_b64:
            raise ExtractionError("No se pudo construir un contexto (markdown ni imagen) utilizable para el LLM")

        schema_str = _default_extraction_prompt(effective_schema)
        institution_suffix = f" del portal de {institution_name}" if institution_name else ""

        from datetime import UTC, datetime

        hoy = datetime.now(UTC).strftime("%Y-%m-%d")
        fecha_minima_iso = (datetime.now(UTC) - __import__("datetime").timedelta(days=90)).strftime("%Y-%m-%d")

        system_prompt = (
            "Eres un agente de extracción de datos estructurados especializado en convocatorias "
            "y fondos de financiamiento para proyectos del ecosistema chileno. "
            "Devuelves únicamente JSON válido, sin comentarios ni texto adicional."
        )

        prompt_text = (
            f"Analiza el siguiente documento Markdown y la captura de pantalla adjunta{institution_suffix} ({base_url}).\n\n"
            "OBJETIVO:\n"
            "Extrae SOLO convocatorias, fondos o programas que entreguen financiamiento directo a terceros.\n\n"
            f"FECHA DE REFERENCIA: {hoy}. Fecha mínima de relevancia: {fecha_minima_iso}.\n\n"
            "ESQUEMA OBLIGATORIO:\n"
            f"{schema_str}\n\n"
            f"DOCUMENTO:\n{markdown_content}"
        )

        # Preparamos el mensaje multimodal si hay imagen
        content_payload: list[dict[str, Any]] = [{"type": "text", "text": prompt_text}]
        if screenshot_b64:
            content_payload.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
                }
            )

        response_text = await self.chat_completion(
            content_payload if screenshot_b64 else prompt_text,
            system_prompt=system_prompt,
            timeout=self.request_timeout_seconds,
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
            chars=len(markdown_content),
        )
        return items

    async def extract_single_detail(
        self,
        html_content: str,
        base_url: str,
        institution_name: str = "",
        max_content_chars: int | None = None,
        institution_hint: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Extrae datos profundos (DetalleEnriquecido) de una página de detalle.

        El LLM SOLO puede escribir en los campos de DetalleEnriquecido.
        No tiene acceso ni puede modificar campos principales (region, monto, etc.).
        institution_hint es contexto adicional por institución proveniente del YAML.
        """
        budget = max_content_chars or self.max_content_chars
        markdown_content = _build_markdown_context(
            html_content=html_content,
            base_url=base_url,
            selectors=None,
            max_chars=budget,
        )

        if not markdown_content.strip():
            logger.warning("Contenido HTML vacío tras limpiar, cancelando extracción.", base_url=base_url)
            return None

        institution_suffix = f" de {institution_name}" if institution_name else ""
        hint_block = f"\n\nCONTEXTO INSTITUCIONAL:\n{institution_hint}" if institution_hint else ""

        system_prompt = (
            "Eres un analista experto en fondos de financiamiento público chileno. "
            "Lees bases y descripciones de convocatorias y extraes información estructurada "
            "con precisión quirurgica, sin inventar nada. "
            "Devuelves únicamente JSON válido, sin comentarios ni texto adicional."
            f"{hint_block}"
        )

        from datetime import UTC, datetime
        hoy = datetime.now(UTC).strftime("%Y-%m-%d")

        prompt_text = (
            f"Analiza la página de convocatoria{institution_suffix} ({base_url}).\n"
            f"Fecha de referencia: {hoy}.\n\n"
            "Extrae el siguiente JSON. Usa null si el campo no aparece explícitamente en el texto.\n"
            "NUNCA inventes datos. Si no está escrito, es null o [].\n\n"
            "{\n"
            '  "requisitos_postulacion": [\n'
            '    "Requisito 1 con texto exacto del documento",\n'
            '    "Requisito 2"\n'
            "  ],\n"
            '  "rubros_financiables": [\n'
            '    "Gasto o rubro que financia el fondo"\n'
            "  ],\n"
            '  "restricciones_excluyentes": [\n'
            '    "Condición que descalifica automáticamente una postulación"\n'
            "  ],\n"
            '  "tipo_beneficiario": "PYME | Persona natural | Municipio | Cooperativa | Empresa | null",\n'
            '  "monto_maximo": "Monto en texto original, ej: $50.000.000 o null",\n'
            '  "porcentaje_subsidio": "Porcentaje que cubre el fondo, ej: 80% o null",\n'
            '  "plazo_ejecucion_meses": 12,\n'
            '  "cobertura_geografica": "Nacional | nombre de región o null",\n'
            '  "fecha_cierre_texto": "Texto original de la fecha de cierre o null",\n'
            '  "cita_evidencia": "Cita textual del documento que respalda los campos anteriores o null"\n'
            "}\n\n"
            f"DOCUMENTO:\n{markdown_content}"
        )

        response_text = await self.chat_completion(
            prompt_text,
            system_prompt=system_prompt,
            timeout=self.request_timeout_seconds,
        )

        parsed = _extract_json_from_text(response_text)
        if isinstance(parsed, dict):
            return parsed

        logger.error("LLM no retornó JSON estructurado válido para detalle", base_url=base_url)
        return None

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

    async def heal_selectors(
        self,
        html_content: str,
        institution_name: str,
        base_url: str,
    ) -> dict[str, str] | None:
        """
        Analiza el HTML para sugerir nuevos selectores CSS cuando los actuales fallan.
        """

        markdown_content = _build_markdown_context(
            html_content=html_content,
            base_url=base_url,
            selectors=None,
            max_chars=self.max_content_chars,
        )

        system_prompt = (
            "Eres un experto en Web Scraping y selectores CSS. "
            "Tu objetivo es identificar la estructura de una lista de convocatorias."
        )
        prompt = (
            f"Portal: {institution_name} ({base_url})\n\n"
            "Analiza el Markdown y entrega selectores CSS para extraer:\n"
            "1. contenedor_items: el selector que agrupa cada fila/caja de convocatoria.\n"
            "2. titulo: selector relativo al contenedor para el nombre del fondo.\n"
            "3. link_detalle: selector relativo para el link.\n\n"
            "Responde SOLO JSON:\n"
            '{"contenedor_items": "...", "titulo": "...", "link_detalle": "..."}\n\n'
            f"CONTENIDO:\n{markdown_content}"
        )

        try:
            response_text = await self.chat_completion(prompt, system_prompt=system_prompt)
            parsed = _extract_json_from_text(response_text)
            if isinstance(parsed, dict) and "contenedor_items" in parsed:
                logger.info("Selectores sanados por LLM", source=institution_name, selectors=parsed)
                return {k: str(v) for k, v in parsed.items()}
        except Exception as exc:
            logger.warning("Fallo al sanar selectores con LLM", source=institution_name, exc=exc)

        return None


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


def _extract_json_list(text: str) -> list[dict[str, str]]:
    """Parsea una respuesta LLM como lista de diccionarios."""
    parsed = _extract_json_from_text(text)
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    raise ScrapingError(f"No se pudo extraer lista JSON de la respuesta: {text[:200]}")


def _extract_json_dict(text: str) -> dict | None:
    """Parsea una respuesta LLM como diccionario."""
    parsed = _extract_json_from_text(text)
    if isinstance(parsed, dict):
        return parsed
    return None


class CommandCodeClient(StructuredLLMClient):
    """Cliente LLM que usa el CLI `cmd` de CommandCode como backend.

    Ejecuta el binario `cmd -p <prompt> -m <modelo>` vía subprocess.
    Es el proveedor primario cuando CMD_API_KEY está configurada.
    """

    provider_name = "commandcode"
    max_content_chars = 100_000
    max_output_tokens = 4_096
    request_timeout_seconds = 120

    def __init__(self) -> None:
        self.api_key = settings.CMD_API_KEY
        self.model = settings.CMD_LLM_MODEL

    def _call_cmd(self, prompt: str, timeout: int = 60) -> str:
        """Ejecuta `cmd -p <prompt> -m <modelo>` y retorna stdout."""
        import os  # noqa: PLC0415
        import shutil  # noqa: PLC0415
        import subprocess  # noqa: PLC0415

        cmd_path = shutil.which("cmd")
        if not cmd_path:
            # Fallback: buscar en nvm
            nvm_dir = os.path.expanduser("~/.nvm/versions/node")
            if os.path.isdir(nvm_dir):
                for v in sorted(os.listdir(nvm_dir), reverse=True):
                    candidate = os.path.join(nvm_dir, v, "bin", "cmd")
                    if os.path.isfile(candidate):
                        cmd_path = candidate
                        break

        if not cmd_path:
            raise ScrapingError("Comando `cmd` no encontrado en PATH ni en ~/.nvm/versions/node/*/bin/")

        env = os.environ.copy()
        if self.api_key:
            env["CMD_API_KEY"] = self.api_key

        try:
            result = subprocess.run(
                [cmd_path, "-p", prompt, "-m", self.model],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            if result.returncode != 0:
                raise ScrapingError(
                    f"CommandCode CLI error (exit {result.returncode}): {result.stderr[:500]}"
                )
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            raise ScrapingError(f"CommandCode CLI timed out after {timeout}s")  # noqa: B904
        except FileNotFoundError:
            raise ScrapingError(f"Binario `cmd` no encontrado en {cmd_path}")  # noqa: B904

    async def chat_completion(
        self,
        prompt: str,
        system_prompt: str | None = None,
        timeout: int = 60,
    ) -> str:
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        return await asyncio.to_thread(self._call_cmd, full_prompt, timeout)

    async def extract_from_html(
        self,
        html_content: str,
        fields_schema: dict[str, str],
        base_url: str,
        timeout: int = 90,
    ) -> list[dict[str, str]]:
        schema_desc = "\n".join(f"- {k}: {v}" for k, v in fields_schema.items())
        prompt = (
            f"Extrae datos estructurados desde el siguiente HTML.\n"
            f"URL base: {base_url}\n"
            f"Campos solicitados:\n{schema_desc}\n\n"
            f"Responde SOLO con JSON válido (lista de objetos).\n\n{html_content[:self.max_content_chars]}"
        )
        result = await self.chat_completion(prompt, timeout=timeout)
        return _extract_json_list(result)

    async def extract_single_detail(
        self,
        html_content: str,
        base_url: str,
        institution_name: str = "",
        max_content_chars: int | None = None,
    ) -> dict[str, Any] | None:
        budget = max_content_chars or self.max_content_chars
        markdown_content = _build_markdown_context(
            html_content=html_content,
            base_url=base_url,
            selectors=None,
            max_chars=budget,
        )

        if not markdown_content.strip():
            logger.warning("Contenido HTML vacío tras limpiar, cancelando extracción.", base_url=base_url)
            return None

        prompt = (
            f"Analiza la siguiente página de convocatoria del portal de {institution_name} ({base_url}).\n\n"
            "Debes extraer la siguiente estructura JSON EXACTA:\n"
            "{\n"
            '  "requisitos_postulacion": ["req 1", "req 2"],\n'
            '  "rubros_financiables": ["rubro 1", "rubro 2"],\n'
            '  "restricciones_excluyentes": ["restriccion 1"],\n'
            '  "cita_evidencia": "Cita textual que justifica la respuesta"\n'
            "}\n\n"
            "REGLAS:\n"
            "1. Si no hay información sobre algún campo, retorna una lista vacía `[]`.\n"
            "2. Si no encuentras evidencia textual explícita, `cita_evidencia` debe ser `null`.\n"
            "3. NO inventes información.\n\n"
            f"DOCUMENTO:\n{markdown_content}"
        )

        try:
            result = await self.chat_completion(prompt, timeout=120)
            parsed = _extract_json_from_text(result)
            if isinstance(parsed, dict):
                return parsed
        except Exception as exc:
            logger.error("Fallo extracción deep scraping con cmd", exc=exc)

        return None

    async def heal_selectors(
        self,
        html_content: str,
        institution_name: str,
        base_url: str,
        timeout: int = 90,
    ) -> dict | None:
        prompt = (
            f"Eres un experto en selectores CSS. Dado el HTML de {institution_name} ({base_url}), "
            f"encuentra selectores CSS que apunten a cada ítem de convocatoria/fondo.\n"
            f"Responde SOLO con JSON: {{\"contenedor_items\": \"...\", \"titulo\": \"...\", "
            f"\"link_detalle\": \"...\", \"identificador\": \"...\"}}\n\n{html_content[:self.max_content_chars]}"
        )
        result = await self.chat_completion(prompt, timeout=timeout)
        return _extract_json_dict(result)


def build_llm_client(preferred_provider: str | None = None) -> StructuredLLMClient:
    """Factory explícita para elegir proveedor LLM sin acoplar la capa de scraping.

    Jerarquía:
    1. CommandCode (primario, si CMD_API_KEY existe)
    2. NVIDIA (si NVIDIA_API_KEY existe)
    3. Groq (si GROQ_API_KEY existe)
    4. OpenRouter (fallback general)
    """

    provider = (preferred_provider or settings.LLM_PROVIDER).strip().lower()

    import shutil

    if provider == "commandcode":
        if shutil.which("cmd"):
            return CommandCodeClient()
        else:
            logger.warning("LLM_PROVIDER es commandcode pero no se encontró 'cmd' en PATH. Usando OpenRouter como fallback.")
            return OpenRouterClient()
    if provider == "nvidia":
        return NvidiaClient()
    if provider == "groq":
        return GroqClient()
    if provider == "openrouter":
        return OpenRouterClient()

    import shutil

    # auto: CommandCode > NVIDIA > Groq > OpenRouter
    if settings.CMD_API_KEY and shutil.which("cmd"):
        return CommandCodeClient()
    if settings.NVIDIA_API_KEY:
        return NvidiaClient()
    if settings.GROQ_API_KEY:
        return GroqClient()
    if settings.OPENROUTER_API_KEY or settings.LLM_API_KEY:
        return OpenRouterClient()

    logger.warning("No hay API key configurada para LLMs; se usará OpenRouter por defecto")
    return OpenRouterClient()
