# Dockerfile
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Instalar dependencias del sistema para Playwright y PostgreSQL
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc \
       libpq-dev \
       curl \
       gnupg \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias de Python
COPY pyproject.toml .
RUN pip install .

# Instalar navegadores de Playwright y sus dependencias de sistema
# Usamos solo chromium para mantener la imagen lo más liviana posible
RUN playwright install --with-deps chromium

# Copiar el resto del código
COPY . .

# Comando por defecto
CMD ["python", "--version"]
