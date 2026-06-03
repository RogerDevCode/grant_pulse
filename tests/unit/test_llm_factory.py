"""Tests para el factory de LLM y los proveedores."""

from unittest.mock import MagicMock, patch

import pytest

from src.infra.llm.client import (
    GroqClient,
    NvidiaClient,
    OpenRouterClient,
    build_llm_client,
)


def _make_settings(**overrides: object) -> MagicMock:
    """Crea un mock de settings donde los atributos no seteados son falsy."""
    mock = MagicMock()
    mock.LLM_PROVIDER = "auto"
    mock.NVIDIA_API_KEY = None
    mock.GROQ_API_KEY = None
    mock.OPENROUTER_API_KEY = None
    mock.LLM_API_KEY = None
    for key, value in overrides.items():
        setattr(mock, key, value)
    return mock


def test_build_llm_client_auto_nvidia():
    with patch("src.infra.llm.client.settings", _make_settings(NVIDIA_API_KEY="nvapi-test")):
        client = build_llm_client()
        assert isinstance(client, NvidiaClient)


def test_build_llm_client_auto_groq():
    with patch(
        "src.infra.llm.client.settings",
        _make_settings(GROQ_API_KEY="gsk_test", NVIDIA_API_KEY=None),
    ):
        client = build_llm_client()
        assert isinstance(client, GroqClient)
        assert not isinstance(client, NvidiaClient)


def test_build_llm_client_auto_openrouter():
    with patch(
        "src.infra.llm.client.settings",
        _make_settings(OPENROUTER_API_KEY="sk-or-test", NVIDIA_API_KEY=None, GROQ_API_KEY=None),
    ):
        client = build_llm_client()
        assert isinstance(client, OpenRouterClient)
        assert not isinstance(client, NvidiaClient)


def test_build_llm_client_explicit_groq():
    with patch("src.infra.llm.client.settings", _make_settings(LLM_PROVIDER="groq")):
        client = build_llm_client()
        assert isinstance(client, GroqClient)


def test_build_llm_client_explicit_nvidia():
    with patch("src.infra.llm.client.settings", _make_settings(LLM_PROVIDER="nvidia")):
        client = build_llm_client()
        assert isinstance(client, NvidiaClient)


@pytest.mark.asyncio
async def test_groq_client_headers():
    with patch("src.infra.llm.client.settings", _make_settings(GROQ_API_KEY="gsk_test")):
        client = GroqClient()
        headers = client._build_headers()
        assert headers["Authorization"] == "Bearer gsk_test"
        assert "X-Title" in headers
