"""Tests para la configuración de la aplicación."""

from src.infra.config import Settings


def test_settings_normalizes_sslmode_for_asyncpg() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgres://grantpulse:grantpulse@db:5432/grantpulse?sslmode=require",
    )

    assert settings.DATABASE_URL == "postgresql+asyncpg://grantpulse:grantpulse@db:5432/grantpulse?ssl=require"
