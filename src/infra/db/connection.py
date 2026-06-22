"""
Gestión de conexión asíncrona a la base de datos.
El proyecto utiliza exclusivamente PostgreSQL (via asyncpg).
Cualquier URL provista por el entorno (ej. Railway) es normalizada en config.py
para asegurar el uso del driver asíncrono.
"""

from collections.abc import AsyncGenerator
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.domain.exceptions import PersistenceError
from src.infra.config import settings
from src.infra.logging import get_logger

logger = get_logger(__name__)

try:
    kwargs: dict[str, Any] = {"echo": False, "future": True}
    kwargs["connect_args"] = {"server_settings": {"jit": "off"}, "statement_cache_size": 0}
    kwargs.update(pool_pre_ping=True, pool_recycle=180, pool_size=5, max_overflow=10, pool_timeout=30)

    engine = create_async_engine(settings.DATABASE_URL, **kwargs)

    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
except Exception as e:
    msg = f"Error al inicializar el motor de base de datos: {e}"
    logger.error(msg, database_url=settings.DATABASE_URL, exc=e)
    raise PersistenceError(msg) from e


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    """Generador asíncrono de sesiones de base de datos para inyección de dependencias."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except SQLAlchemyError as e:
            await session.rollback()
            msg = f"Error de transacción de base de datos: {e}"
            logger.error(msg, exc=e)
            raise PersistenceError(msg) from e
        except HTTPException:
            raise
        except Exception as e:
            await session.rollback()
            msg = f"Error inesperado en la sesión de base de datos: {e}"
            logger.error(msg, exc=e)
            raise PersistenceError(msg) from e
