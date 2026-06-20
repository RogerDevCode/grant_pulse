FROM python:3.13-slim AS builder
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON=python3.13 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc \
       libpq-dev \
       curl \
       gnupg \
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
       lsb-release \
       wget \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh -s -- \
    && mkdir -p /ms-playwright
ENV PATH="/root/.local/bin:${PATH}"
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --directory /app --python 3.13 --link-mode copy \
    && chmod -R u+x /app/.venv/bin
RUN /app/.venv/bin/python -m playwright install --with-deps chromium

FROM python:3.13-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH="/root/.local/bin:/usr/local/bin:/usr/bin:/bin"
WORKDIR /app
RUN mkdir -p /ms-playwright
COPY --from=builder /root/.local/bin /root/.local/bin
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /ms-playwright /ms-playwright
COPY pyproject.toml ./
COPY src ./src
COPY rules ./rules
USER root
CMD ["/app/.venv/bin/grantpulse-api", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
