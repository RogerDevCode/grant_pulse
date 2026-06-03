"""
Instancia principal de la aplicación FastAPI.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.infra.logging import get_logger
from src.presentation.api.routes import router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:  # noqa: ARG001
    # Setup global (si fuera necesario e.g. pools de colas)
    logger.info("Iniciando aplicación API GrantPulse")
    yield
    # Cleanup global
    logger.info("Cerrando aplicación API GrantPulse")


def create_app() -> FastAPI:
    app = FastAPI(
        title="GrantPulse API",
        description="API para monitorear fondos de financiamiento institucionales.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Configurar CORS (permitir todos para desarrollo, restringir en prod)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Incluir las rutas
    app.include_router(router)

    # Servir archivos estáticos del frontend
    frontend_path = Path(__file__).parent.parent / "frontend"
    if frontend_path.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

        @app.get("/", include_in_schema=False)
        async def read_index() -> FileResponse:  # pyright: ignore[reportUnusedFunction]
            return FileResponse(frontend_path / "index.html")

    return app


app = create_app()
