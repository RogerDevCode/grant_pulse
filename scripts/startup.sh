#!/bin/sh
# startup.sh — Script de arranque para Railway.
# Ejecuta migraciones con retry explícito antes de levantar la API.
# Logs a stdout para visibilidad en Railway.

set -e

echo "[startup] ======================================="
echo "[startup] GrantPulse API - Startup"
echo "[startup] ======================================="
echo "[startup] DATABASE_URL prefix: $(echo "${DATABASE_URL:-NOT_SET}" | cut -c1-30)..."
echo "[startup] ENV: ${ENV:-dev}"

# Esperar a que la BD esté lista (máx 60s)
echo "[startup] Esperando disponibilidad de la base de datos..."
MAX_WAIT=60
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if /app/.venv/bin/python -c "
import asyncio, os, sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        print('ERROR: DATABASE_URL no definida', flush=True)
        sys.exit(1)
    for prefix, replacement in [('postgres://', 'postgresql+asyncpg://'), ('postgresql://', 'postgresql+asyncpg://')]:
        if url.startswith(prefix):
            url = url.replace(prefix, replacement, 1)
    engine = create_async_engine(url, connect_args={'ssl': 'require'} if 'railway' in url.lower() else {})
    try:
        async with engine.connect() as conn:
            await conn.execute(text('SELECT 1'))
        await engine.dispose()
        print('DB ready', flush=True)
    except Exception as e:
        await engine.dispose()
        raise

asyncio.run(check())
" 2>/dev/null; then
        echo "[startup] Base de datos disponible."
        break
    fi
    echo "[startup] BD no disponible aún, reintentando en 3s... (${WAITED}s/${MAX_WAIT}s)"
    sleep 3
    WAITED=$((WAITED + 3))
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "[startup] ERROR: La base de datos no estuvo disponible en ${MAX_WAIT}s."
    exit 1
fi

# Aplicar drift fix (idempotente: detecta estado real de la BD y stampa alembic)
echo "[startup] Aplicando fix de drift alembic..."
/app/.venv/bin/python scripts/fix_alembic_drift.py
echo "[startup] Drift fix completado."

# Aplicar migraciones pendientes
echo "[startup] Aplicando migraciones (alembic upgrade head)..."
/app/.venv/bin/alembic upgrade head
echo "[startup] Migraciones aplicadas correctamente."

echo "[startup] ======================================="
echo "[startup] Iniciando Uvicorn / GrantPulse API..."
echo "[startup] ======================================="

exec /app/.venv/bin/grantpulse-api
