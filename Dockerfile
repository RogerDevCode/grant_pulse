# syntax=docker/dockerfile:1
FROM python:3.13-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON=python3.13 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-group dev --directory /app \
    && chmod -R u+x /app/.venv/bin

# Install Playwright browsers (headless chromium) — necesario para scraping
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.venv/ms-playwright
RUN /app/.venv/bin/playwright install chromium \
    && rm -rf /root/.cache /tmp/*

# ── Runtime stage ──
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app" \
    PATH="/app/.venv/bin:/usr/local/bin:/usr/bin:/bin" \
    PORT="8000" \
    PLAYWRIGHT_BROWSERS_PATH="/app/.venv/ms-playwright" \
    DATABASE_URL="sqlite+aiosqlite:///data/grantpulse.db"

WORKDIR /app

# Crear directorio de datos persistente (Railway Volume lo monta aquí si se configura)
RUN mkdir -p /app/data \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
    && /app/.venv/bin/playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
COPY pyproject.toml ./
COPY src ./src
COPY rules ./rules
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

EXPOSE 8000

# Railway inyecta $PORT dinámicamente — el entrypoint lo respeta vía os.environ.get("PORT", "8000")
CMD ["/app/.venv/bin/grantpulse-api"]
