"""
Dependencias de FastAPI para inyección (Base de datos, Repositorios).
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.domain.ports import ConvocatoriaRepository
from src.infra.db.connection import get_db_session
from src.infra.db.repository import SQLConvocatoriaRepository

# Alias tipado para la sesión
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_convocatoria_repo(session: DbSession) -> ConvocatoriaRepository:
    """Inyecta el repositorio concreto basado en SQLAlchemy."""
    return SQLConvocatoriaRepository(session)


ConvocatoriaRepoDep = Annotated[ConvocatoriaRepository, Depends(get_convocatoria_repo)]
