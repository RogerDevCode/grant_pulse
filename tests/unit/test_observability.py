"""Tests para el contexto de corrida (run_id) y su inyección automática en logs."""

from __future__ import annotations

from src.core.application.run_context import clear_run_id, get_run_id, new_run_id
from src.infra.logging import GrantPulseLogger


class TestRunContext:
    def test_new_run_id_returns_hex_string(self) -> None:
        clear_run_id()
        run_id = new_run_id()
        assert isinstance(run_id, str)
        assert len(run_id) == 12
        assert run_id.isalnum()

    def test_new_run_id_generates_unique_ids(self) -> None:
        clear_run_id()
        first = new_run_id()
        second = new_run_id()
        assert first != second

    def test_get_run_id_returns_current_after_set(self) -> None:
        clear_run_id()
        run_id = new_run_id()
        assert get_run_id() == run_id

    def test_get_run_id_creates_new_if_empty(self) -> None:
        clear_run_id()
        run_id = get_run_id()
        assert isinstance(run_id, str)
        assert len(run_id) == 12

    def test_clear_run_id_resets_to_empty(self) -> None:
        new_run_id()
        clear_run_id()
        after_clear = get_run_id()
        assert len(after_clear) == 12
        assert after_clear != ""


class TestLoggerEnrichment:
    def test_enrich_injects_run_id_when_active(self) -> None:
        clear_run_id()
        run_id = new_run_id()
        logger_instance = GrantPulseLogger("test.enrich")
        enriched = logger_instance._enrich({"fuente": "corfo"})  # noqa: SLF001
        assert enriched["run_id"] == run_id
        assert enriched["fuente"] == "corfo"

    def test_enrich_creates_run_id_if_none(self) -> None:
        clear_run_id()
        logger_instance = GrantPulseLogger("test.enrich.auto")
        enriched = logger_instance._enrich({"key": "val"})  # noqa: SLF001
        assert "run_id" in enriched
        assert len(enriched["run_id"]) == 12

    def test_enrich_does_not_overwrite_explicit_run_id(self) -> None:
        clear_run_id()
        new_run_id()
        logger_instance = GrantPulseLogger("test.enrich.explicit")
        enriched = logger_instance._enrich({"run_id": "custom-123"})  # noqa: SLF001
        assert enriched["run_id"] == "custom-123"

    def test_enrich_empty_context_gets_run_id(self) -> None:
        clear_run_id()
        run_id = new_run_id()
        logger_instance = GrantPulseLogger("test.enrich.empty")
        enriched = logger_instance._enrich({})  # noqa: SLF001
        assert enriched == {"run_id": run_id}
