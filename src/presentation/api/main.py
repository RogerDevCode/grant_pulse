"""
Instancia principal de la aplicación FastAPI.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.core.domain.exceptions import GrantPulseError, PersistenceError
from src.infra.config import settings
from src.infra.logging import get_logger
from src.presentation.api.routes import router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:  # noqa: ARG001
    logger.info("Iniciando aplicación API GrantPulse")

    import asyncio

    from src.infra.cli import sync_all_rules

    asyncio.create_task(sync_all_rules())

    yield
    logger.info("Cerrando aplicación API GrantPulse")


def _get_cors_origins() -> list[str]:
    if settings.ENV == "prod":
        return ["https://grantpulse.cl"]
    return ["http://localhost:8000", "http://localhost:3000", "http://127.0.0.1:8000"]


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(PersistenceError)
    async def persistence_error_handler(request: Request, exc: PersistenceError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        logger.error("Error de persistencia en request", path=request.url.path, method=request.method, exc=exc)
        return JSONResponse(status_code=503, content={"detail": "Error de persistencia. Intente nuevamente."})

    @app.exception_handler(GrantPulseError)
    async def grantpulse_error_handler(request: Request, exc: GrantPulseError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        logger.error("Error de dominio en request", path=request.url.path, method=request.method, exc=exc)
        return JSONResponse(status_code=500, content={"detail": "Error interno del servidor."})


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

    _register_exception_handlers(app)

    @app.get("/health", tags=["Health"])
    async def healthcheck() -> JSONResponse: # pyright: ignore[reportUnusedFunction]
        checks: dict[str, str] = {"status": "ok", "env": settings.ENV}
        db_ok = False
        try:
            from sqlalchemy import text

            from src.infra.db.connection import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            db_ok = True
        except Exception as exc:
            logger.error("Healthcheck: DB no disponible", exc=exc)
            checks["db"] = "unavailable"

        if db_ok:
            checks["db"] = "ok"
        else:
            return JSONResponse(status_code=503, content=checks)

        return JSONResponse(status_code=200, content=checks)

    app.include_router(router)

    frontend_path = Path(__file__).parent.parent / "frontend"
    if frontend_path.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

        @app.get("/", include_in_schema=False)
        async def read_index() -> FileResponse:  # pyright: ignore[reportUnusedFunction]
            return FileResponse(frontend_path / "index.html")

    return app


app = create_app()
