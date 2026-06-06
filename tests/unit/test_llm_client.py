"""
Tests unitarios del módulo LLM: parsing multi-estrategia y normalización de items.
Estos tests NO hacen llamadas de red reales (todo mockeado).
"""

import json

import pytest

from src.infra.llm.client import _extract_json_from_text, _normalize_items  # pyright: ignore[reportPrivateUsage]


class _NoopRateLimiter:
    async def wait(self) -> float:
        return 0.0


async def _noop_sleep(_delay: float) -> None:
    return None


# ──────────────────────────────────────────────────────────────
# Tests para _extract_json_from_text
# ──────────────────────────────────────────────────────────────


class TestExtractJsonFromText:
    def test_pure_json_object(self) -> None:
        """Estrategia 1: JSON puro como objeto."""
        text = '{"items": [{"titulo": "Fondo Semilla"}]}'
        result = _extract_json_from_text(text)
        assert result == {"items": [{"titulo": "Fondo Semilla"}]}

    def test_pure_json_list(self) -> None:
        """Estrategia 1: JSON puro como lista."""
        text = '[{"id": "F001"}, {"id": "F002"}]'
        result = _extract_json_from_text(text)
        assert result == [{"id": "F001"}, {"id": "F002"}]

    def test_json_in_markdown_block_with_language(self) -> None:
        """Estrategia 2: JSON dentro de un bloque ```json ... ```."""
        text = 'Aquí tu resultado:\n```json\n{"items": []}\n```\nEso es todo.'
        result = _extract_json_from_text(text)
        assert result == {"items": []}

    def test_json_in_plain_markdown_block(self) -> None:
        """Estrategia 3: JSON dentro de un bloque ``` sin especificar lenguaje."""
        text = 'Resultado:\n```\n{"fondos": [1, 2, 3]}\n```'
        result = _extract_json_from_text(text)
        assert result == {"fondos": [1, 2, 3]}

    def test_json_embedded_in_prose(self) -> None:
        """Estrategia 4: JSON embebido en texto libre."""
        text = 'El modelo dice: aquí va la info {"items": [{"titulo": "Test"}]} fin del mensaje.'
        result = _extract_json_from_text(text)
        assert result == {"items": [{"titulo": "Test"}]}

    def test_array_embedded_in_prose(self) -> None:
        """Estrategia 4: Array JSON embebido en texto libre."""
        text = 'Resultados: [{"id": "C01", "titulo": "Convocatoria 1"}] — generados por IA.'
        result = _extract_json_from_text(text)
        assert result == [{"id": "C01", "titulo": "Convocatoria 1"}]

    def test_invalid_json_returns_none(self) -> None:
        """Texto completamente inválido debe retornar None."""
        result = _extract_json_from_text("No hay JSON aquí, sólo texto libre.")
        assert result is None

    def test_empty_string_returns_none(self) -> None:
        result = _extract_json_from_text("")
        assert result is None

    def test_json_with_surrounding_whitespace(self) -> None:
        """JSON con espacios en blanco al inicio y fin."""
        text = '   \n  {"key": "value"}  \n  '
        result = _extract_json_from_text(text)
        assert result == {"key": "value"}


# ──────────────────────────────────────────────────────────────
# Tests para _normalize_items
# ──────────────────────────────────────────────────────────────


class TestNormalizeItems:
    def test_standard_items_key(self) -> None:
        """Clave canónica 'items'."""
        raw = {"items": [{"titulo": "A"}, {"titulo": "B"}]}
        result = _normalize_items(raw)
        assert len(result) == 2
        assert result[0]["titulo"] == "A"

    def test_convocatorias_key(self) -> None:
        """Clave alternativa 'convocatorias'."""
        raw = {"convocatorias": [{"titulo": "Fondo X"}]}
        result = _normalize_items(raw)
        assert result == [{"titulo": "Fondo X"}]

    def test_fondos_key(self) -> None:
        """Clave alternativa 'fondos'."""
        raw = {"fondos": [{"id": "F01"}]}
        result = _normalize_items(raw)
        assert result == [{"id": "F01"}]

    def test_results_key(self) -> None:
        """Clave alternativa 'results'."""
        raw = {"results": [{"id": "1"}, {"id": "2"}]}
        result = _normalize_items(raw)
        assert len(result) == 2

    def test_data_key(self) -> None:
        """Clave alternativa 'data'."""
        raw = {"data": [{"titulo": "Alpha"}]}
        result = _normalize_items(raw)
        assert result[0]["titulo"] == "Alpha"

    def test_direct_list(self) -> None:
        """El LLM devuelve directamente una lista."""
        raw = [{"titulo": "Item 1"}, {"titulo": "Item 2"}, {"titulo": "Item 3"}]
        result = _normalize_items(raw)
        assert len(result) == 3

    def test_list_filters_non_dict(self) -> None:
        """Lista con elementos mezclados: sólo se retienen los dicts."""
        raw = [{"titulo": "Válido"}, "string_inválido", 42, None]
        result = _normalize_items(raw)
        assert result == [{"titulo": "Válido"}]

    def test_unknown_key_fallback(self) -> None:
        """Si la clave no está en la lista canónica, busca la primera lista de dicts."""
        raw = {"lista_especial": [{"titulo": "X"}], "meta": {"total": 1}}
        result = _normalize_items(raw)
        assert result == [{"titulo": "X"}]

    def test_empty_items(self) -> None:
        """Lista vacía de items."""
        raw: dict[str, list[str]] = {"items": []}
        result = _normalize_items(raw)
        assert result == []

    def test_none_returns_empty(self) -> None:
        """Input None o no-dict/list retorna vacío."""
        assert _normalize_items(None) == []
        assert _normalize_items("texto") == []
        assert _normalize_items(42) == []


# ──────────────────────────────────────────────────────────────
# Tests de integración del cliente (mockeado con respx)
# ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_completion_cascada_modelo_falla() -> None:
    """
    Verifica que el cliente salta al siguiente modelo cuando el primero retorna 429.
    """
    import respx
    from httpx import Response

    from src.infra.llm.client import OpenRouterClient

    # Creamos un cliente con 2 modelos ficticios
    client = OpenRouterClient()
    client.api_key = "test-key-123"
    client.models = ["modelo-a:free", "modelo-b:free"]
    client._rate_limiter = _NoopRateLimiter()  # type: ignore[assignment]
    client._sleep = _noop_sleep  # type: ignore[assignment]

    payload_ok = json.dumps({"choices": [{"message": {"content": '{"items": []}'}}]})

    with respx.mock:
        # Primer modelo retorna 429 (cuota)
        respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
            side_effect=[
                Response(429, text="Rate limit exceeded"),
                Response(200, text=payload_ok),
            ]
        )

        result = await client.chat_completion("test prompt")
        assert result == '{"items": []}'


@pytest.mark.asyncio
async def test_chat_completion_todos_modelos_fallan_lanza_scraping_error() -> None:
    """
    Verifica que se lanza ScrapingError cuando todos los modelos fallan.
    """
    import respx
    from httpx import Response

    from src.core.domain.exceptions import ScrapingError
    from src.infra.llm.client import OpenRouterClient

    client = OpenRouterClient()
    client.api_key = "test-key-123"
    client.models = ["modelo-a:free", "modelo-b:free"]
    client._rate_limiter = _NoopRateLimiter()  # type: ignore[assignment]
    client._sleep = _noop_sleep  # type: ignore[assignment]

    with respx.mock:
        respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
            return_value=Response(503, text="Service unavailable")
        )

    with pytest.raises(ScrapingError, match="FALLO_LLM_TOTAL"):
        await client.chat_completion("test prompt")


@pytest.mark.asyncio
async def test_chat_completion_sin_api_key_lanza_scraping_error() -> None:
    """
    Verifica que sin API Key se lanza ScrapingError inmediatamente.
    """
    from src.core.domain.exceptions import ScrapingError
    from src.infra.llm.client import OpenRouterClient

    client = OpenRouterClient()
    client.api_key = None
    client._rate_limiter = _NoopRateLimiter()  # type: ignore[assignment]
    client._sleep = _noop_sleep  # type: ignore[assignment]

    with pytest.raises(ScrapingError, match="OPENROUTER_API_KEY"):
        await client.chat_completion("test prompt")
