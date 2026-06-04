"""
Instancia principal de la aplicación FastAPI.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.infra.config import settings
from src.infra.logging import get_logger
from src.presentation.api.routes import router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]: # noqa: ARG001
    logger.info("Iniciando aplicación API GrantPulse")
    
    # Ejecutar búsqueda inicial automáticamente en background
    import asyncio
    from src.infra.cli import sync_all_rules
    asyncio.create_task(sync_all_rules())

    yield
    logger.info("Cerrando aplicación API GrantPulse")


def _get_cors_origins() -> list[str]:
    if settings.ENV == "prod":
        return ["https://grantpulse.cl"]
    return ["http://localhost:8000", "http://localhost:3000", "http://127.0.0.1:8000"]


def create_app() -> FastAPI:
    app = FastAPI(
        title="GrantPulse API",
        description="API para monitorear fondos de financiamiento institucionales.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_get_cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.get("/health", tags=["Health"])
    async def healthcheck() -> JSONResponse:
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "env": settings.ENV},
        )

    app.include_router(router)

    frontend_path = Path(__file__).parent.parent / "frontend"
    if frontend_path.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

    @app.get("/", include_in_schema=False)
    async def read_index() -> FileResponse: # pyright: ignore[reportUnusedFunction]
        return FileResponse(frontend_path / "index.html")

    return app


app = create_app()
