"""
Servicios de dominio que orquestan lógica de negocio compleja, como la detección de cambios.
"""

from typing import Any

from src.core.domain.entities import Convocatoria, Delta, EventoCambio, Fuente
from src.core.domain.exceptions import RuleEngineError
from src.infra.logging import get_logger

logger = get_logger(__name__)


class ChangeDetectorService:
    """
    Servicio de dominio para comparar listas de convocatorias extraídas
    contra el estado anterior y determinar qué ha cambiado.
    """

    @staticmethod
    def detect_changes(
        nuevas_convocatorias: list[Convocatoria], antiguas_convocatorias: dict[str, Convocatoria], fuente: Fuente
    ) -> list[EventoCambio]:
        """
        Compara las convocatorias nuevas con las antiguas.
        Devuelve una lista de EventoCambio que deben ser procesados/notificados.
        Las convocatorias antiguas deben estar indexadas por su identificador_externo.
        """
        logger.info("Iniciando detección de cambios", fuente_id=str(fuente.id))
        eventos: list[EventoCambio] = []
        alertas_config = fuente.configuracion_reglas.alertas

        try:
            for nueva in nuevas_convocatorias:
                identificador = nueva.identificador_externo
                antigua = antiguas_convocatorias.get(identificador)

                if not antigua:
                    # Es una apertura nueva
                    evento = EventoCambio(
                        convocatoria_id=nueva.id,
                        tipo="APERTURA",
                        es_relevante=True,  # Toda apertura se considera relevante
                    )
                    eventos.append(evento)
                    continue

                # Sincronizamos el ID para mantener integridad relacional
                nueva.id = antigua.id

                # Si existe, comparamos campos
                deltas = ChangeDetectorService._compare_fields(antigua, nueva, alertas_config.ignorar_cambios_en)

                if deltas:
                    # Determinar relevancia basado en campos sensibles
                    es_relevante = any(d.campo in alertas_config.campos_sensibles for d in deltas)

                    evento = EventoCambio(
                        convocatoria_id=nueva.id,
                        tipo="MODIFICACION",
                        deltas=deltas,
                        es_relevante=es_relevante,
                    )
                    eventos.append(evento)

        except Exception as e:
            msg = f"Error en el motor de reglas detectando cambios para fuente {fuente.id}: {e}"
            logger.error(msg, exc=e)
            raise RuleEngineError(msg) from e

        return eventos

    @staticmethod
    def _compare_fields(antigua: Convocatoria, nueva: Convocatoria, campos_ignorados: list[str]) -> list[Delta]:
        """
        Compara atributo a atributo (exceptuando campos ignorados y metadatos internos).
        """
        deltas: list[Delta] = []

        # Lista explícita de campos de negocio a comparar
        campos_a_comparar = ["titulo", "descripcion", "url_detalle", "estado", "fecha_cierre", "monto"]

        for campo in campos_a_comparar:
            if campo in campos_ignorados:
                continue

            val_antiguo: Any = getattr(antigua, campo)
            val_nuevo: Any = getattr(nueva, campo)

            if val_antiguo != val_nuevo:
                deltas.append(
                    Delta(
                        campo=campo,
                        valor_anterior=str(val_antiguo) if val_antiguo is not None else None,
                        valor_nuevo=str(val_nuevo) if val_nuevo is not None else None,
                    )
                )

        return deltas
