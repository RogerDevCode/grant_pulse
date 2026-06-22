"""
Instancia principal de la aplicación FastAPI.
"""
# ruff: noqa: E402

import os

# Desactivar variables de entorno de proxy que rompen curl_cffi en Railway
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)

# Asegurar que el directorio de datos existe
os.makedirs("data", exist_ok=True)

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

    # Crear tablas si no existen — usa el mismo engine de la app, evita thread-safety issues con aiosqlite
    try:
        from src.infra.db.connection import engine
        from src.infra.db.models import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Tablas de base de datos verificadas/creadas exitosamente")
    except Exception as e:
        logger.warning("No se pudieron verificar tablas", exc=e)

    # Sincronizar reglas YAML → BD de forma síncrona antes de aceptar requests
    try:
        from src.infra.cli import sync_all_rules

        await sync_all_rules()
        logger.info("Reglas sincronizadas exitosamente")
    except Exception as e:
        logger.warning("Error en sync inicial de reglas (no crítico)", exc=e)

    yield
    logger.info("Cerrando aplicación API GrantPulse")


def _get_cors_origins() -> list[str]:
    base = [
        "https://grantpulse.cl",
        "https://grant-pulse-production.up.railway.app",
        "https://grant_pulse-production.up.railway.app",
    ]
    # Permite agregar orígenes extra desde la variable RAILWAY_URL o CORS_ORIGINS
    extra = os.environ.get("CORS_ORIGINS", "")
    if extra:
        base.extend([o.strip() for o in extra.split(",") if o.strip()])
    if settings.ENV != "prod":
        base += ["http://localhost:8000", "http://localhost:3000", "http://127.0.0.1:8000"]
    return base


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
    async def healthcheck() -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
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


def run() -> None:
    """Entry point usado por Railway y `grantpulse-api` CLI."""
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("src.presentation.api.main:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run()
