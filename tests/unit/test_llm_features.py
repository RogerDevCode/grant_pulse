from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from src.infra.config import settings
from src.infra.llm.client import OpenRouterClient


@pytest.fixture
def llm_client() -> OpenRouterClient:
    client = OpenRouterClient()

    class _NoopRateLimiter:
        async def wait(self) -> float:
            return 0.0

    async def _noop_sleep(_delay: float) -> None:
        return None

    client._rate_limiter = _NoopRateLimiter()  # type: ignore[assignment]
    client._sleep = _noop_sleep  # type: ignore[assignment]
    return client


@pytest.mark.asyncio
async def test_discovery_navigation_brain(llm_client: OpenRouterClient) -> None:
    """
    Característica 1: Navigation Brain (Discovery step).
    Verifica que procesa el HTML y extrae correctamente la URL devuelta por la IA.
    """
    html = """
    <html>
        <body>
            <nav>
                <a href="/sobre-nosotros">Sobre Nosotros</a>
                <a href="/convocatorias-abiertas">Convocatorias Abiertas</a>
            </nav>
        </body>
    </html>
    """
    # Mockeamos chat_completion para que retorne el JSON que daría la IA
    with patch.object(llm_client, "chat_completion", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = '{"discovered_url": "https://agencia.cl/convocatorias-abiertas"}'

        result = await llm_client.discover_funding_url(html, "https://agencia.cl")

        assert result == "https://agencia.cl/convocatorias-abiertas"
        mock_chat.assert_called_once()
        # Verificar que el prompt incluye el markdown generado
        prompt_sent = mock_chat.call_args[0][0]
        assert "Convocatorias Abiertas" in prompt_sent


@pytest.mark.asyncio
async def test_high_density_context_cleaning(llm_client: OpenRouterClient) -> None:
    """
    Característica 2: High-Density Context (Limpieza de HTML sucio y conversión a Markdown).
    Verifica que scripts, estilos y ruido son removidos y no llegan a la IA.
    """
    html_sucio = """
    <html>
        <head>
            <style>.hidden { display: none; }</style>
            <script>alert("Hola");</script>
        </head>
        <body>
            <nav>Menu inútil</nav>
            <div class="cookie-banner">Acepta las cookies</div>
            <h1>Fondo de Innovación 2026</h1>
            <p>Postula ahora.</p>
            <footer>Copyright 2026</footer>
        </body>
    </html>
    """
    with patch.object(llm_client, "chat_completion", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = '{"items": [{"titulo": "Fondo de Innovación 2026"}]}'

        await llm_client.extract_from_html(html_sucio, {}, "https://test.cl")

        prompt_sent = mock_chat.call_args[0][0]
        # El ruido debe haber sido eliminado
        assert "alert" not in prompt_sent
        assert "display: none" not in prompt_sent
        assert "Menu inútil" not in prompt_sent
        assert "Acepta las cookies" not in prompt_sent
        assert "Copyright" not in prompt_sent
        # Lo importante debe estar
        assert "Fondo de Innovación 2026" in prompt_sent
        assert "Postula ahora" in prompt_sent


@pytest.mark.asyncio
async def test_context_budget_is_respected(llm_client: OpenRouterClient) -> None:
    """
    Característica 3: Context budget.
    Verifica que el contexto se acota alrededor de 100k caracteres.
    """
    # Generamos un HTML enorme
    big_paragraph = "<p>Contenido importante que debe leer la IA.</p>" * 15000  # ~750k caracteres HTML
    html_masivo = f"<html><body>{big_paragraph}</body></html>"

    with patch.object(llm_client, "chat_completion", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = '{"items": []}'

        await llm_client.extract_from_html(html_masivo, {}, "https://test.cl")

        prompt_sent = mock_chat.call_args[0][0]
        # El prompt completo debe quedar muy por debajo del HTML original.
        assert len(prompt_sent) < 120_000
        assert "Contenido importante que debe leer la IA." in prompt_sent


@pytest.mark.asyncio
@respx.mock
async def test_resilient_failthru_cascada(llm_client: OpenRouterClient) -> None:
    """
    Característica 4: Resilient Failthru (Cascada de modelos).
    Verifica que al recibir 404, 429 o 502 de un modelo, el sistema automáticamente
    intenta con el siguiente hasta tener éxito.
    """
    api_url = "https://openrouter.ai/api/v1/chat/completions"

    llm_client.models = [
        "modelo-a:free",
        "modelo-b:free",
        "modelo-c:free",
        "modelo-d:free",
    ]

    # Configuramos el mock para que responda secuencialmente con errores
    # y luego con éxito para probar la cascada completa
    route = respx.post(api_url)

    route.side_effect = [
        httpx.Response(404, json={"error": "Model not found"}),  # Falla modelo 1
        httpx.Response(429, json={"error": "Rate limit"}),  # Falla modelo 2
        httpx.Response(502, json={"error": "Bad Gateway"}),  # Falla modelo 3
        httpx.Response(
            200, json={"choices": [{"message": {"content": '{"items": [{"titulo": "Éxito"}]}'}}]}
        ),  # Modelo 4 tiene éxito
    ]

    settings.OPENROUTER_API_KEY = "test_key"

    # Esto activará la cascada iterando sobre los modelos de config.py
    resultado = await llm_client.chat_completion("Prompt", "System", timeout=5)

    assert '{"items": [{"titulo": "Éxito"}]}' in resultado
    # Se debe haber llamado a la API 4 veces
    assert route.call_count == 4
