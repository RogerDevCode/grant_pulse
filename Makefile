PYTHON ?= uv run python

.PHONY: up down restart logs migrate db-shell test lint format typecheck validate clean

up:
	@APP_PORT=$$($(PYTHON) -m src.infra.port_utils 8000) docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

migrate:
	docker compose exec api sh -c "cd /app && /app/.venv/bin/alembic upgrade head"

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
	@echo "Limpiando archivos temporales..."
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@find . -type d -name ".ruff_cache" -exec rm -rf {} +
	@find . -type d -name ".mypy_cache" -exec rm -rf {} +
	@echo "Hecho."
