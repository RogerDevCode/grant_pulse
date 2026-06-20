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
       libglib2.0-0 \
       libnss3 \
       libnspr4 \
       libx11-6 \
       libx11-xcb1 \
       libxcomposite1 \
       libxdamage1 \
       libxrandr2 \
       libgbm1 \
       libgtk-3-0 \
       libcups2 \
       libatk1.0-0 \
       libcairo2 \
       libdrm2 \
       libxss1 \
       libxtst6 \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv \
    && uv --version \
    && mkdir -p /ms-playwright

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --directory /app --python 3.13 --link-mode copy \
    && chmod -R u+x /app/.venv/bin

# ── Optional: Playwright browsers (only if installed) ──
RUN /app/.venv/bin/python -m playwright install --with-deps chromium 2>/dev/null \
    && mkdir -p /ms-playwright \
    && echo "Playwright installed" \
    || echo "Playwright skipped (no browser scraping)"

# ── Runtime stage ──
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app" \
    PATH="/app/.venv/bin:/usr/local/bin:/usr/bin:/bin" \
    PORT="8000"

WORKDIR /app

RUN mkdir -p /app/data \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /ms-playwright /ms-playwright
COPY pyproject.toml ./
COPY src ./src
COPY rules ./rules
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
    CMD /app/.venv/bin/python -c "from urllib.request import urlopen; urlopen('http://localhost:8000/health')" || exit 1

CMD ["/app/.venv/bin/grantpulse-api"]
