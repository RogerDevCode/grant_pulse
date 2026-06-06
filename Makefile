PYTHON ?= ./venv/bin/python

.PHONY: up down restart logs migrate db-shell test lint format typecheck validate clean

up:
	@export APP_PORT=$$($(PYTHON) -m src.infra.port_utils 8000); \
	export DB_PORT=$$($(PYTHON) -m src.infra.port_utils 5432); \
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

migrate:
	docker compose exec api alembic upgrade head

db-shell:
	docker compose exec db psql -U grantpulse -d grantpulse

test:
	$(PYTHON) -m pytest tests/ -q

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .

typecheck:
	$(PYTHON) -m mypy src/ tests/
	$(PYTHON) -m pyright src/ tests/

validate: lint typecheck test
	@echo "All validations passed!"

clean:
	@echo "Limpiando archivos temporales y caché..."
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@find . -type d -name ".ruff_cache" -exec rm -rf {} +
	@find . -type d -name ".mypy_cache" -exec rm -rf {} +
	@echo "Reseteando datos de monitoreo en la base de datos (preservando configuraciones)..."
	@docker compose up -d db > /dev/null 2>&1
	@echo "Esperando a que la base de datos esté lista..."
	@sleep 3
	@docker compose exec -T db psql -U grantpulse -d grantpulse -c "TRUNCATE TABLE notificaciones, historial_cambios, snapshots, convocatorias, fuentes CASCADE;"
	@echo "Hecho. Se han borrado fuentes, convocatorias e historiales, pero se mantienen tus canales de Telegram y Email."
