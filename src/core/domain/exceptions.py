"""
Jerarquía de excepciones del sistema GrantPulse.
Define errores específicos y tipados para evitar el uso de excepciones genéricas.
"""


class GrantPulseError(Exception):
    """Excepción base para todos los errores del sistema GrantPulse."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigurationError(GrantPulseError):
    """Se lanza cuando hay un error en la configuración general o en los archivos YAML."""

    pass


class DomainError(GrantPulseError):
    """Excepción base para violaciones de reglas de negocio."""

    pass


class ValidationError(DomainError):
    """Se lanza cuando los datos de entrada o entidades no cumplen con el esquema o restricciones."""

    pass


class ScrapingError(GrantPulseError):
    """Excepción base para fallos en el proceso de descarga y parsing."""

    pass


class NetworkError(ScrapingError):
    """Se lanza cuando falla la conexión de red o el servidor responde con error."""

    pass


class ExtractionError(ScrapingError):
    """Se lanza cuando cambian los selectores CSS y no se pueden parsear los elementos."""

    pass


class NormalizationError(ScrapingError):
    """Se lanza cuando falla la conversión de formatos de fecha, moneda u otros campos."""

    pass


class RuleEngineError(GrantPulseError):
    """Se lanza cuando ocurre un error procesando o comparando las reglas de cambio."""

    pass


class PersistenceError(GrantPulseError):
    """Se lanza ante fallos en la capa de persistencia (PostgreSQL/SQLAlchemy)."""

    pass


class NotificationError(GrantPulseError):
    """Se lanza cuando falla el envío de alertas (Telegram, Email, etc.)."""

    pass
