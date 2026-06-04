"""
Gestión de conexión asíncrona a PostgreSQL 17 mediante SQLAlchemy 2.0.
"""

from collections.abc import AsyncGenerator

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
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
except Exception as e:
    msg = f"Error al inicializar el motor de base de datos asíncrono: {e}"
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
