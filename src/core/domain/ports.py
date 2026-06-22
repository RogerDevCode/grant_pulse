"""
Definición de puertos (interfaces abstractas) para la capa de persistencia de GrantPulse.
Permite desacoplar las reglas de negocio de los detalles de base de datos.
"""

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from src.core.domain.entities import Convocatoria, EventoCambio, Fuente, NotificacionResult, Snapshot


class FuenteRepository(ABC):
    """Interfaz contractual para interactuar con la persistencia de Fuentes."""

    @abstractmethod
    async def get_by_id(self, fuente_id: int) -> Fuente | None:
        """Obtiene una fuente por su ID único."""
        pass

    @abstractmethod
    async def get_by_nombre(self, nombre: str) -> Fuente | None:
        """Obtiene una fuente por su nombre único."""
        pass

    @abstractmethod
    async def get_all_active(self) -> list[Fuente]:
        """Obtiene todas las fuentes que se encuentran activas."""
        pass

    @abstractmethod
    async def save(self, fuente: Fuente) -> Fuente:
        """Guarda o actualiza una fuente en la persistencia."""
        pass


class SnapshotRepository(ABC):
    """Interfaz contractual para interactuar con la persistencia de Snapshots."""

    @abstractmethod
    async def save(self, snapshot: Snapshot) -> Snapshot:
        """Guarda un nuevo snapshot en el sistema."""
        pass

    @abstractmethod
    async def get_latest_by_fuente(self, fuente_id: int | str | UUID) -> Snapshot | None:
        """Obtiene el último snapshot guardado de una fuente en particular."""
        pass


class ConvocatoriaRepository(ABC):
    """Interfaz contractual para interactuar con la persistencia de Convocatorias."""

    @abstractmethod
    async def get_by_fuente_and_externo(
        self, fuente_id: int | str | UUID, identificador_externo: str
    ) -> Convocatoria | None:
        """Obtiene una convocatoria específica usando el ID de la fuente y el ID externo del portal."""
        pass

    @abstractmethod
    async def get_all_by_fuente(self, fuente_id: int | str | UUID) -> list[Convocatoria]:
        """Obtiene todas las convocatorias guardadas para una fuente específica."""
        pass

    @abstractmethod
    async def save(self, convocatoria: Convocatoria) -> Convocatoria:
        """Guarda o actualiza una convocatoria."""
        pass

    @abstractmethod
    async def save_evento_cambio(self, evento: EventoCambio, snapshot_id: int | str | UUID) -> EventoCambio:
        """Registra un evento de cambio asociado a una convocatoria y snapshot específicos."""
        pass

    @abstractmethod
    async def save_metadatos(self, convocatoria: Convocatoria) -> None:
        """Actualiza exclusivamente el campo metadatos de una convocatoria existente.

        Contrato: no toca ninguno de los campos obtenidos por el scraper
        (region, monto, fecha_apertura, fecha_cierre, estado, titulo, descripcion).
        Uso exclusivo del enricher/LLM para no pisar datos ya verificados.
        """
        pass

    @abstractmethod
    async def flush(self) -> None:
        """Flushea los cambios pendientes en la sesión para que sean visibles dentro de la misma transacción."""
        pass


class ScraperPort(ABC):
    """Interfaz contractual para los motores de extracción (Scrapers)."""

    @abstractmethod
    async def fetch(self, fuente: Fuente) -> Snapshot:
        """
        Descarga el contenido de la fuente y genera un Snapshot crudo.
        Debe fallar rápido (NetworkError) si el sitio está caído.
        """
        pass

    @abstractmethod
    async def extract(self, snapshot: Snapshot, fuente: Fuente, **kwargs: Any) -> list[dict[str, str | None]]:
        """
        Extrae datos estructurados desde un Snapshot crudo usando las reglas de la Fuente.
        Devuelve una lista de diccionarios planos con los campos extraídos.
        Falla (ExtractionError) si el contrato del HTML cambió drásticamente.
        """
        pass


class NotificationPort(ABC):
    """Interfaz contractual para el envío de alertas y notificaciones."""

    @abstractmethod
    async def notify_event(
        self, evento: EventoCambio, convocatoria: Convocatoria, fuente: Fuente
    ) -> NotificacionResult:
        """
        Envía una notificación sobre un evento de cambio en una convocatoria.
        Retorna un NotificacionResult con el estado del envío.
        Debe lanzar NotificationError solo para fallos catastróficos de configuración.
        """
        pass


class NotificacionRepository(ABC):
    """Interfaz contractual para persistir resultados de notificaciones."""

    @abstractmethod
    async def save(self, resultado: NotificacionResult) -> NotificacionResult:
        """Persiste el resultado de un intento de notificación."""
        pass


class LLMPort(ABC):
    """Puerto abstracto para servicios de lenguaje grande (LLM).
    Permite intercambiar proveedores (CommandCode, OpenRouter, NVIDIA, Groq)
    sin acoplar la capa de dominio a implementaciones concretas."""

    @abstractmethod
    async def chat_completion(
        self,
        prompt: str,
        system_prompt: str | None = None,
        timeout: int = 60,
    ) -> str:
        """Envía un prompt y recibe una respuesta textual del LLM."""
        pass

    @abstractmethod
    async def extract_from_html(
        self,
        html_content: str,
        fields_schema: dict[str, str],
        base_url: str,
        timeout: int = 90,
    ) -> list[dict[str, str]]:
        """Extrae campos estructurados desde HTML usando el LLM."""
        pass

    @abstractmethod
    async def extract_single_detail(
        self,
        html_content: str,
        base_url: str,
        institution_name: str = "",
        max_content_chars: int | None = None,
        institution_hint: str | None = None,
    ) -> dict[str, Any] | None:
        """Extrae datos profundos de una página de detalle."""
        pass

    @abstractmethod
    async def heal_selectors(
        self,
        html_content: str,
        institution_name: str,
        base_url: str,
        timeout: int = 90,
    ) -> dict[str, object] | None:
        """Re-intenta descubrir selectores CSS cuando los configurados fallan."""
        pass
