"""
Tests unitarios para la jerarquía de excepciones de GrantPulse.
"""

import pytest

from src.core.domain.exceptions import (
    ConfigurationError,
    DomainError,
    ExtractionError,
    GrantPulseError,
    NetworkError,
    NormalizationError,
    ScrapingError,
    ValidationError,
)


def test_exception_inheritance() -> None:
    """Verifica que todas las excepciones heredan correctamente de GrantPulseError."""
    assert issubclass(ConfigurationError, GrantPulseError)
    assert issubclass(DomainError, GrantPulseError)
    assert issubclass(ValidationError, DomainError)
    assert issubclass(ScrapingError, GrantPulseError)
    assert issubclass(NetworkError, ScrapingError)
    assert issubclass(ExtractionError, ScrapingError)
    assert issubclass(NormalizationError, ScrapingError)


def test_exception_message() -> None:
    """Verifica que el mensaje de error se almacene y propague de forma adecuada."""
    msg = "Error crítico de prueba"
    exc = ConfigurationError(msg)

    assert exc.message == msg
    assert str(exc) == msg

    with pytest.raises(ConfigurationError) as exc_info:
        raise ConfigurationError("Fallo de configuración")
    assert str(exc_info.value) == "Fallo de configuración"
