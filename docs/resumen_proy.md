# GrantPulse — Resumen de Proyecto

## Core
Monitoreo y detección de cambios en convocatorias de fondos públicos chilenos (CORFO, ANID, etc.). Detección de aperturas y cambios de estado/fecha/monto. Alertas vía Telegram/Email.

## Stack
- Backend: Python 3.13, FastAPI, SQLAlchemy 2, PostgreSQL 17, Alembic.
- Scraping: Estático (CSS selectors), JSON APIs, Browser (Playwright), LLM (OpenRouter/Nemotron) como fallback.
- Frontend: Single Page Application (Vanilla JS + CSS moderno).

## Arquitectura
Capas desacopladas:
- `src/core/domain`: Entidades (`entities.py`), excepciones (`exceptions.py`).
- `src/infra`: Módulos de scraping (`infra/scraping/`), carga de YAMLs (`rules_loader.py`), BD/ORM (`db/models.py`, `db/repository.py`), CLI (`cli.py`), configuración (`config.py`).
- `src/presentation`: API (`api/main.py`), frontend (`frontend/app.js`).

## Reglas y Fuentes
- Configuración en YAML (`rules/*.yaml`).
- Sincronización local vía `grantpulse-sync` (YAML->BD).
- Catálogo estático en `infra/sources/catalog.py` sobrescribe BD al sincronizar.
