"""
Contexto de corrida (correlation ID) para trazabilidad operacional.

Provee un run_id que acompaña todos los logs de un ciclo de monitoreo,
permitiendo correlacionar eventos across scrape → detect → notify.
"""

from contextvars import ContextVar
from uuid import uuid4

_run_id: ContextVar[str] = ContextVar("run_id", default="")


def new_run_id() -> str:
    run_id = uuid4().hex[:12]
    _run_id.set(run_id)
    return run_id


def get_run_id() -> str:
    current = _run_id.get()
    if not current:
        return new_run_id()
    return current


def clear_run_id() -> None:
    _run_id.set("")
