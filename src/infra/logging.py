"""
Módulo de logging estructurado de GrantPulse.
Configura el logging del sistema para inyectar contexto operacional (run_id, fuente_id, etc.).
"""

import json
import logging
import sys
from typing import Any, cast

from src.infra.config import settings


class StructuredFormatter(logging.Formatter):
    """Formateador de log estructurado en JSON para fácil ingesta e indexación."""

    def __init__(self) -> None:
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        # Estructura base del log
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Agregar contexto extra inyectado a través del parámetro 'extra'
        extra_ctx = getattr(record, "extra_context", None)
        if isinstance(extra_ctx, dict):
            typed_ctx = cast(dict[str, Any], extra_ctx)
            for k, v in typed_ctx.items():
                log_data[k] = v

        # Si hay datos de excepción, los formateamos
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


class StructuredLocalFormatter(logging.Formatter):
    """Formateador estructurado simplificado y coloreado para visualización local en consola."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        level = record.levelname
        msg = record.getMessage()

        context_str = ""
        extra_ctx = getattr(record, "extra_context", None)
        if isinstance(extra_ctx, dict):
            typed_ctx = cast(dict[str, Any], extra_ctx)
            context_str = " | " + " ".join(f"{k}={v}" for k, v in typed_ctx.items())

        exc_str = ""
        if record.exc_info:
            exc_str = f"\n{self.formatException(record.exc_info)}"

        return f"[{timestamp}] {level:<7} {record.name}: {msg}{context_str}{exc_str}"


def configure_logging() -> None:
    """Configura el logging raíz del sistema según el entorno."""
    root_logger = logging.getLogger()

    # Evitar duplicar handlers
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    # Seleccionar formateador por entorno
    if settings.ENV == "prod":
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(StructuredLocalFormatter())

    root_logger.addHandler(handler)

    # Asignar nivel desde settings
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root_logger.setLevel(log_level)


class GrantPulseLogger:
    """Clase envolvente sobre el logger estándar para forzar el uso de contexto estructurado.

    Inyecta automáticamente run_id en cada entrada de log si existe
    un contexto de corrida activo.
    """

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def _enrich(self, context: dict[str, Any]) -> dict[str, Any]:
        from src.core.application.run_context import get_run_id

        run_id = get_run_id()
        if run_id and "run_id" not in context:
            context = {**context, "run_id": run_id}
        return context

    def debug(self, msg: str, **context: Any) -> None:
        self._logger.debug(msg, extra={"extra_context": self._enrich(context)})

    def info(self, msg: str, **context: Any) -> None:
        self._logger.info(msg, extra={"extra_context": self._enrich(context)})

    def warning(self, msg: str, **context: Any) -> None:
        self._logger.warning(msg, extra={"extra_context": self._enrich(context)})

    def error(self, msg: str, exc: Exception | None = None, **context: Any) -> None:
        enriched = self._enrich(context)
        if exc:
            self._logger.error(msg, exc_info=exc, extra={"extra_context": enriched})
        else:
            self._logger.error(msg, extra={"extra_context": enriched})


def get_logger(name: str) -> GrantPulseLogger:
    """Obtiene una instancia del logger estructurado."""
    return GrantPulseLogger(name)


# Inicializar automáticamente al importar el módulo
configure_logging()
