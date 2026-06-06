"""Tests para el healthcheck con verificación de DB."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.presentation.api.main import create_app


class _FakeAsyncSession:
    """Fake AsyncSession that works as async context manager."""

    def __init__(self, execute_return: object | None = None, execute_side_effect: BaseException | None = None) -> None:
        if execute_side_effect:
            self.execute = AsyncMock(side_effect=execute_side_effect)
        else:
            self.execute = AsyncMock(return_value=execute_return)

    async def __aenter__(self) -> _FakeAsyncSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


class _FakeSessionFactory:
    """Pseudo async_sessionmaker replacement."""

    def __init__(self, execute_return: object | None = None, execute_side_effect: BaseException | None = None) -> None:
        self._execute_return = execute_return
        self._execute_side_effect = execute_side_effect

    def __call__(self) -> _FakeAsyncSession:
        return _FakeAsyncSession(
            execute_return=self._execute_return,
            execute_side_effect=self._execute_side_effect,
        )


def _patch_session_local(fake_factory: _FakeSessionFactory) -> object:
    connection_module: ModuleType = sys.modules["src.infra.db.connection"]
    original = getattr(connection_module, "AsyncSessionLocal")  # noqa: B009
    setattr(connection_module, "AsyncSessionLocal", fake_factory)  # noqa: B010
    return original


def _restore_session_local(original: object) -> None:
    connection_module: ModuleType = sys.modules["src.infra.db.connection"]
    setattr(connection_module, "AsyncSessionLocal", original)  # noqa: B010


class TestHealthcheck:
    @pytest.mark.asyncio
    async def test_healthcheck_db_ok_returns_200(self) -> None:
        fake_factory = _FakeSessionFactory(execute_return=None)
        original = _patch_session_local(fake_factory)
        try:
            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health")
        finally:
            _restore_session_local(original)

        assert response.status_code == 200
        data = response.json()
        assert data["db"] == "ok"
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_healthcheck_db_unavailable_returns_503(self) -> None:
        fake_factory = _FakeSessionFactory(execute_side_effect=Exception("connection refused"))
        original = _patch_session_local(fake_factory)
        try:
            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health")
        finally:
            _restore_session_local(original)

        assert response.status_code == 503
        data = response.json()
        assert data["db"] == "unavailable"
