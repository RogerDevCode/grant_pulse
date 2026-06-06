"""
Entidades y modelos de dominio principales de GrantPulse.
Utiliza Pydantic para asegurar la validación estricta y tipado fuerte de configuraciones.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl


class SelectorConfig(BaseModel):
    """Configuración de selectores CSS para extraer campos de una página web."""

    contenedor_items: str = Field(..., description="Selector CSS para el contenedor de cada convocatoria")
    identificador: str = Field(..., description="Selector CSS para el identificador único o atributo")
    titulo: str = Field(..., description="Selector CSS para el título de la convocatoria")
    descripcion: str | None = Field(default=None, description="Selector CSS para la descripción corta")
    link_detalle: str | None = Field(default=None, description="Selector CSS para el enlace de detalle")
    estado: str | None = Field(default=None, description="Selector CSS para el estado de la convocatoria")
    fecha_cierre: str | None = Field(default=None, description="Selector CSS para la fecha de cierre")
    monto: str | None = Field(default=None, description="Selector CSS para el monto máximo")
    region: str | None = Field(default=None, description="Selector CSS para la región")


class JsonMappingConfig(BaseModel):
    """Configuración de mapeo para extraer campos de una respuesta JSON."""

    root_path: str | None = Field(default=None, description="Ruta al listado de items (ej: 'data.concursos')")
    identificador: str = Field(..., description="Path al ID único (ej: 'id' o 'metadata.uuid')")
    titulo: str = Field(..., description="Path al título")
    descripcion: str | None = Field(default=None, description="Path a la descripción")
    link_detalle: str | None = Field(default=None, description="Path al enlace de detalle")
    estado: str | None = Field(default=None, description="Path al estado")
    fecha_apertura: str | None = Field(default=None, description="Path a la fecha de apertura de la convocatoria")
    fecha_cierre: str | None = Field(default=None, description="Path a la fecha de cierre")
    monto: str | None = Field(default=None, description="Path al monto")
    region: str | None = Field(default=None, description="Path a la región")
    agrupar_por: str | None = Field(default=None, description="Path para agrupar items duplicados (ej: 'idInstrumento')")
    paginacion: "PaginationConfig" = Field(default_factory=lambda: PaginationConfig(), description="Configuración de paginación")


class PaginationConfig(BaseModel):
    """Configuración de paginación para APIs JSON tipo WordPress."""

    total_pages_header: str | None = Field(default=None, description="Header con el total de páginas (ej: 'X-WP-TotalPages')")
    total_items_header: str | None = Field(default=None, description="Header con el total de items (ej: 'X-WP-Total')")
    page_param: str = Field(default="page", description="Nombre del query param para la página")
    per_page_param: str = Field(default="per_page", description="Nombre del query param para items por página")
    max_pages: int = Field(default=50, description="Límite de seguridad para evitar loops infinitos")


class NormalizerItem(BaseModel):
    """Parámetros para normalizar un campo de texto extraído."""

    regex_extraction: str | None = Field(default=None, description="Regex para extraer el subtexto de interés")
    formato_salida: str | None = Field(default=None, description="Formato esperado si es fecha u otro tipo")
    idioma: str | None = Field(default="es", description="Idioma para el formateador de fechas")


class NormalizerConfig(BaseModel):
    """Mapeo de normalizadores para campos específicos."""

    titulo: NormalizerItem | None = None
    fecha_cierre: NormalizerItem | None = None
    monto: NormalizerItem | None = None
    region: NormalizerItem | None = None


class AlertsConfig(BaseModel):
    """Configuración de qué campos gatillan notificaciones al alterarse."""

    campos_sensibles: list[str] = Field(default_factory=list, description="Campos que disparan alerta al cambiar")
    ignorar_cambios_en: list[str] = Field(default_factory=list, description="Campos decorativos a ignorar")


class RulesConfig(BaseModel):
    """Configuración general de scraping y reglas de una fuente (Sitio Web)."""

    nombre: str = Field(..., description="Nombre identificador de la fuente (ej. CORFO)")
    url_busqueda: HttpUrl = Field(..., description="URL completa de búsqueda o listado")
    estrategia: str = Field(default="html_static", description="Estrategia: html_static, json_api")
    selectores: SelectorConfig | None = Field(default=None)
    json_mapping: JsonMappingConfig | None = Field(default=None)
    normalizadores: NormalizerConfig = Field(default_factory=NormalizerConfig)
    alertas: AlertsConfig = Field(default_factory=AlertsConfig)
    region_defecto: str | None = Field(default=None, description="Región por defecto para todas las convocatorias de esta fuente")
    excluir_patrones_url: list[str] = Field(
        default_factory=list,
        description="Patrones de substring en la URL del item para excluirlo (ej: '.pdf', 'cdn.com')",
    )
    excluir_patrones_titulo: list[str] = Field(
        default_factory=list,
        description="Patrones regex en el título del item para excluirlo (ej: '^Bases ', '^Modificación ')",
    )


class Fuente(BaseModel):
    """Entidad de dominio que representa un portal de financiamiento institucional."""

    id: UUID = Field(default_factory=uuid4)
    nombre: str
    url_base: HttpUrl
    configuracion_reglas: RulesConfig
    activa: bool = True
    creado_en: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actualizado_en: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Delta(BaseModel):
    """Representa un cambio específico detectado en un campo de una convocatoria."""

    campo: str
    valor_anterior: str | None = None
    valor_nuevo: str | None = None


class Convocatoria(BaseModel):
    """Entidad estructurada de un fondo de financiamiento extraído."""

    id: UUID = Field(default_factory=uuid4)
    fuente_id: UUID
    identificador_externo: str
    titulo: str
    descripcion: str | None = None
    url_detalle: HttpUrl | None = None
    fecha_apertura: datetime | None = None
    fecha_cierre: datetime | None = None
    monto: float | None = None
    region: str | None = None
    estado: str
    metadatos: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    creado_en: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actualizado_en: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Snapshot(BaseModel):
    """Representa la captura del contenido físico crudo de un portal."""

    id: UUID = Field(default_factory=uuid4)
    fuente_id: UUID
    fecha_captura: datetime = Field(default_factory=lambda: datetime.now(UTC))
    contenido_crudo: str
    hash_contenido: str
    estado_ejecucion: str


class EventoCambio(BaseModel):
    """Representa una alteración calificada en una convocatoria."""

    id: UUID = Field(default_factory=uuid4)
    convocatoria_id: UUID
    tipo: str  # ej: "APERTURA", "MODIFICACION", "OTROS"
    deltas: list[Delta] = Field(default_factory=list[Delta])
    es_relevante: bool = False
    fecha_deteccion: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NotificacionResult(BaseModel):
    """Resultado del intento de envío de una notificación por un canal específico."""

    evento_id: UUID
    canal: str
    destinatario: str
    estado: str  # "ENVIADO", "FALLIDO", "SKIPPED"
    error_log: str | None = None
