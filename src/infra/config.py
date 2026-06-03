"""
Configuración de la aplicación GrantPulse.
Maneja la carga y validación estricta de variables de entorno mediante Pydantic Settings.
"""

from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Estructura de configuraciones del sistema, validada al inicio de la ejecución."""

    # Entorno y logs
    ENV: str = Field(default="dev", description="Entorno actual: dev, test, prod")
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Nivel de logs: DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )

    # Base de Datos
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://booking:booking@localhost:5432/booking",
        description="URL de conexión asíncrona a la base de datos PostgreSQL",
    )

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def enforce_asyncpg(cls, v: Any) -> Any:
        if isinstance(v, str):
            # Normalizar postgres:// a postgresql://
            if v.startswith("postgres://"):
                v = v.replace("postgres://", "postgresql://", 1)
            # Forzar el uso del driver asíncrono asyncpg
            if v.startswith("postgresql://"):
                v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # Alertas Telegram (Opcional en desarrollo)
    TELEGRAM_BOT_TOKEN: str | None = Field(default=None, description="Token de la API del bot de Telegram")
    TELEGRAM_CHAT_ID: str | None = Field(default=None, description="ID del chat/canal para notificaciones")

    # Alertas Email (Opcional en desarrollo)
    SMTP_HOST: str | None = Field(default=None, description="Servidor SMTP para envío de correos")
    SMTP_PORT: int = Field(default=587, description="Puerto del servidor SMTP")
    SMTP_USER: str | None = Field(default=None, description="Usuario de SMTP")
    SMTP_PASSWORD: str | None = Field(default=None, description="Contraseña de SMTP")
    SMTP_FROM_EMAIL: str | None = Field(default=None, description="Remitente de los correos")

    # Configuración de archivos de reglas
    RULES_DIR: str = Field(default="rules", description="Ruta al directorio de reglas YAML")

    # Proveedor LLM preferido
    LLM_PROVIDER: str = Field(
        default="auto",
        description="Proveedor LLM preferido: auto, groq u openrouter",
    )

    # Soporte LLM — OpenRouter
    LLM_API_KEY: str | None = Field(default=None, description="Alias de OPENROUTER_API_KEY (legacy)")
    OPENROUTER_API_KEY: str | None = Field(default=None, description="API Key para OpenRouter")
    OPENROUTER_SITE_URL: str = Field(
        default="https://grantpulse.cl",
        description="URL del sitio, enviada en headers HTTP-Referer a OpenRouter",
    )

    # Soporte LLM — NVIDIA
    NVIDIA_API_KEY: str | None = Field(default=None, description="API Key para NVIDIA integrate")
    NVIDIA_MODEL: str = Field(default="z-ai/glm-5.1", description="Modelo a usar en NVIDIA")
    NVIDIA_BASE_URL: str = Field(default="https://integrate.api.nvidia.com/v1/chat/completions", description="URL completa del endpoint de chat de NVIDIA")

    # Lista de modelos para failover (de mayor a menor prioridad)
    LLM_MODELS_FALLBACK: list[str] = Field(
        default_factory=lambda: [
            "qwen/qwen3-235b-a22b-2507:free",  # 262K context, buen ajuste para extracción estructurada
            "meta-llama/llama-3.3-70b-instruct:free",  # 131K context, fuerte en español y extracción
            "deepseek/deepseek-r1:free",  # 164K context, fallback de razonamiento
        ],
        description="Lista priorizada de modelos para failover en OpenRouter",
    )

    # Máximo de caracteres de contenido a enviar al LLM (protección de contexto)
    LLM_MAX_CONTENT_CHARS: int = Field(
        default=100_000,
        description="Límite de caracteres del contenido Markdown a enviar al LLM",
    )

    # Máximo de tokens de salida por request LLM
    LLM_MAX_OUTPUT_TOKENS: int = Field(
        default=4_096,
        description="Límite de tokens de salida para respuestas estructuradas",
    )

    # Espaciado mínimo entre requests a OpenRouter para no golpear rate limits de free tier
    LLM_MIN_SECONDS_BETWEEN_REQUESTS: float = Field(
        default=8.0,
        description="Pausa mínima entre requests LLM consecutivas",
    )

    # Timeout de request al proveedor LLM
    LLM_REQUEST_TIMEOUT_SECONDS: int = Field(
        default=90,
        description="Timeout por request al proveedor LLM",
    )

    # Soporte LLM — Groq
    GROQ_API_KEY: str | None = Field(default=None, description="API Key para Groq")
    GROQ_SITE_URL: str = Field(
        default="https://grantpulse.cl",
        description="URL del sitio, enviada como contexto del cliente Groq",
    )
    GROQ_MODELS_FALLBACK: list[str] = Field(
        default_factory=lambda: [
            "llama-3.1-8b-instant",  # el modelo más liviano y rápido para extracción estructurada
            "qwen/qwen3-32b",  # mejor razonamiento estructurado si el primero no basta
            "llama-3.3-70b-versatile",  # fallback de mayor capacidad
        ],
        description="Lista priorizada de modelos para failover en Groq",
    )
    GROQ_MAX_CONTENT_CHARS: int = Field(
        default=100_000,
        description="Límite de caracteres del contenido Markdown a enviar al LLM de Groq",
    )
    GROQ_MAX_OUTPUT_TOKENS: int = Field(
        default=4_096,
        description="Límite de tokens de salida para respuestas estructuradas en Groq",
    )
    GROQ_MIN_SECONDS_BETWEEN_REQUESTS: float = Field(
        default=12.0,
        description="Pausa mínima entre requests Groq consecutivas",
    )
    GROQ_REQUEST_TIMEOUT_SECONDS: int = Field(
        default=90,
        description="Timeout por request al proveedor Groq",
    )

    # Configuración de Proxy (Opcional, para evadir bloqueos)
    PROXY_URL: str | None = Field(default=None, description="URL del servidor proxy (ej: http://proxy.host:port)")
    PROXY_USER: str | None = Field(default=None, description="Usuario para autenticación de proxy")
    PROXY_PASS: str | None = Field(default=None, description="Contraseña para autenticación de proxy")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore")


# Instancia única global de configuración. Falla al importar si hay errores de validación (fail-fast).
try:
    settings = Settings()
except Exception as e:
    from src.core.domain.exceptions import ConfigurationError

    raise ConfigurationError(f"Error al inicializar la configuración de la aplicación: {e}") from e
