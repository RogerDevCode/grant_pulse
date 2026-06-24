"""
Instancia principal de la aplicación FastAPI.
"""
# ruff: noqa: E402

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from copy import deepcopy
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


def _build_uvicorn_log_config() -> dict[str, object]:
    """Devuelve una configuración de logging de Uvicorn que emite a stdout."""
    from uvicorn.config import LOGGING_CONFIG

    config = deepcopy(LOGGING_CONFIG)
    handlers = config["handlers"]
    handlers["default"]["stream"] = "ext://sys.stdout"
    handlers["access"]["stream"] = "ext://sys.stdout"
    return config


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:  # noqa: ARG001
    logger.info("Iniciando aplicación API GrantPulse")

    # Forzar ejecución de migraciones en caso de que startCommand sea ignorado en Railway
    try:
        import subprocess
        import sys

        from sqlalchemy import text

        from src.infra.db.connection import AsyncSessionLocal

        logger.info("Aplicando parche de esquema idempotente...")
        async with AsyncSessionLocal() as session:
            await session.execute(text("ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS url_check_failures INTEGER NOT NULL DEFAULT 0"))
            await session.execute(text("ALTER TABLE convocatorias ADD COLUMN IF NOT EXISTS ultimo_check_url TIMESTAMP WITH TIME ZONE"))
            await session.commit()

        logger.info("Verificando y aplicando migraciones de base de datos...")
        # Ejecutar migraciones con timeout para evitar bloqueos en startup
        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    sys.executable, "scripts/fix_alembic_drift.py",
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE
                ),
                timeout=30.0
            )
            await asyncio.wait_for(proc.communicate(), timeout=30.0)
        except TimeoutError:
            logger.warning("Timeout ejecutando fix_alembic_drift.py - continuando de todos modos")
        except Exception as e:
            logger.warning("Error ejecutando fix_alembic_drift.py: %s - continuando de todos modos", e)

        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    sys.executable, "-m", "alembic", "upgrade", "head",
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE
                ),
                timeout=60.0
            )
            await asyncio.wait_for(proc.communicate(), timeout=60.0)
        except TimeoutError:
            logger.warning("Timeout ejecutando alembic upgrade head - continuando de todos modos")
        except Exception as e:
            logger.warning("Error ejecutando alembic upgrade head: %s - continuando de todos modos", e)

        logger.info("Migraciones aplicadas exitosamente")
    except Exception as e:
        logger.error("Error al aplicar parche de esquema o migraciones en el startup", exc=e)
        # No levantamos la excepción para permitir que la aplicación continúe iniciando
        # aunque las migraciones fallen, ya que podrían ser problemas temporales

    # Sincronizar reglas YAML → BD y normalizar URLs en segundo plano después de iniciar
    # Para evitar bloqueos en startup que puedan causar timeouts en health checks
    async def _background_initialization():
        try:
            # Normalizar URLs existentes con timeout
            try:
                from src.infra.maintenance import normalize_existing_urls
                await asyncio.wait_for(normalize_existing_urls(), timeout=60.0)
                logger.info("URLs normalizadas en background")
            except TimeoutError:
                logger.warning("Timeout normalizando URLs - se continuará en segundo plano")
                # Reintentar en segundo plano
                asyncio.create_task(normalize_existing_urls())
            except Exception as e:
                logger.error("Error en normalización inicial: %s", e)
                # Reintentar en segundo plano
                asyncio.create_task(normalize_existing_urls())

            # Sincronizar reglas con timeout
            try:
                from src.infra.cli import sync_all_rules
                await asyncio.wait_for(sync_all_rules(), timeout=60.0)
                logger.info("Reglas sincronizadas en background")
            except TimeoutError:
                logger.warning("Timeout sincronizando reglas - se continuará en segundo plano")
                # Reintentar en segundo plano
                asyncio.create_task(sync_all_rules())
            except Exception as e:
                logger.error("Error en sincronización inicial: %s", e)
                # Reintentar en segundo plano
                asyncio.create_task(sync_all_rules())
        except Exception as e:
            logger.error("Error inesperado en inicialización en background: %s", e)

    # Iniciar inicialización en background para no bloquear el startup
    asyncio.create_task(_background_initialization())

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
        """Healthcheck liviano: responde 200 siempre que el proceso esté en pie.

        La disponibilidad de la DB se reporta como campo informativo, pero no
        bloquea el check. Railway solo necesita saber que Uvicorn levantó.
        """
        checks: dict[str, str] = {"status": "ok", "env": settings.ENV}
        try:
            from sqlalchemy import text

            from src.infra.db.connection import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            checks["db"] = "ok"
        except Exception as exc:
            logger.warning("Healthcheck: DB no disponible", exc=exc)
            checks["db"] = "unavailable"

        # Siempre 200: Railway no debe reiniciar el contenedor por latencia de DB.
        # Si la DB cae, el error aparece en los endpoints reales, no aquí.
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
    uvicorn.run(
        "src.presentation.api.main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        log_config=_build_uvicorn_log_config(),
    )


if __name__ == "__main__":
    run()
