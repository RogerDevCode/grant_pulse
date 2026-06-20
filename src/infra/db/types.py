"""
Tipos de columna personalizados para SQLAlchemy cross-database.
Maneja la conversión UUID ↔ str automáticamente para compatibilidad con SQLite.
"""

import uuid
from typing import Any

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator


class GUID(TypeDecorator):
    """Almacena UUIDs como strings (varchar(36)) en SQLite, compat con PostgreSQL nativo."""

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, str):
            return value
        return str(value)

    def process_result_value(self, value: Any, dialect: Any) -> uuid.UUID | str | None:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        # En SQLite el driver devuelve str, en PostgreSQL devuelve UUID
        if isinstance(value, str):
            try:
                return uuid.UUID(value)
            except ValueError:
                return value
        return value
