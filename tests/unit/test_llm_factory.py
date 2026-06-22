"""Tests para el factory de LLM y los proveedores."""

from typing import Any
from unittest.mock import patch

import pytest

from src.infra.llm.client import (
    GroqClient,
    NvidiaClient,
    OpenRouterClient,
    build_llm_client,
)


class MockSettings:
    def __init__(self, **kwargs: Any) -> None:
        self.LLM_PROVIDER = "auto"
        self.GROQ_MODELS_FALLBACK = ["llama-3.1-8b-instant"]
        self.LLM_MODELS_FALLBACK = ["google/gemini-2.5-flash:free"]
        self.LLM_MIN_SECONDS_BETWEEN_REQUESTS = 0.0
        self.GROQ_MIN_SECONDS_BETWEEN_REQUESTS = 0.0
        for k, v in kwargs.items():
            setattr(self, k, v)
    def __getattr__(self, name: str) -> Any:
        return None

def _make_settings(**overrides: object) -> Any:
    """Crea un mock de settings donde los atributos no seteados son None."""
    return MockSettings(**overrides)


def test_build_llm_client_auto_nvidia() -> None:
    with patch("src.infra.llm.client.settings", _make_settings(NVIDIA_API_KEY="nvapi-test")):
        client = build_llm_client()
        assert isinstance(client, NvidiaClient)


def test_build_llm_client_auto_groq() -> None:
    with patch(
        "src.infra.llm.client.settings",
        _make_settings(GROQ_API_KEY="gsk_test", NVIDIA_API_KEY=None),
    ):
        client = build_llm_client()
        assert isinstance(client, GroqClient)
        assert not isinstance(client, NvidiaClient)


def test_build_llm_client_auto_openrouter() -> None:
    with patch(
        "src.infra.llm.client.settings",
        _make_settings(OPENROUTER_API_KEY="sk-or-test", NVIDIA_API_KEY=None, GROQ_API_KEY=None),
    ):
        client = build_llm_client()
        assert isinstance(client, OpenRouterClient)
        assert not isinstance(client, NvidiaClient)


def test_build_llm_client_explicit_groq() -> None:
    with patch("src.infra.llm.client.settings", _make_settings(LLM_PROVIDER="groq")):
        client = build_llm_client()
        assert isinstance(client, GroqClient)


def test_build_llm_client_explicit_nvidia() -> None:
    with patch("src.infra.llm.client.settings", _make_settings(LLM_PROVIDER="nvidia")):
        client = build_llm_client()
        assert isinstance(client, NvidiaClient)


@pytest.mark.asyncio
async def test_groq_client_headers() -> None:
    with patch("src.infra.llm.client.settings", _make_settings(GROQ_API_KEY="gsk_test")):
        client = GroqClient()
        headers = client._build_headers()
        assert headers["Authorization"] == "Bearer gsk_test"
        assert "X-Title" in headers
