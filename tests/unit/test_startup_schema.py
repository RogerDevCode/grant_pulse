"""Tests para el bootstrap de esquema de la API."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.presentation.api import main as api_main


class _FakeConnection:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.run_sync = AsyncMock(return_value=None)

    async def __aenter__(self) -> _FakeConnection:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, statement: Any) -> None:
        self.executed.append(str(statement))


class _FakeEngine:
    def __init__(self) -> None:
        self.connection = _FakeConnection()

    def begin(self) -> _FakeConnection:
        return self.connection


@pytest.mark.asyncio
async def test_ensure_startup_schema_creates_tables_without_manual_alters(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_engine = _FakeEngine()
    monkeypatch.setattr("src.infra.db.connection.engine", fake_engine)

    await api_main._ensure_startup_schema()

    assert fake_engine.connection.run_sync.await_count == 1
    assert fake_engine.connection.executed == []
