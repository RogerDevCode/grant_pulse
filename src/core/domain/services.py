"""
Servicios de dominio que orquestan lógica de negocio compleja, como la detección de cambios.
"""

from difflib import SequenceMatcher
from typing import Any

try:
    import jellyfish
except ModuleNotFoundError:  # pragma: no cover - depende del entorno
    jellyfish = None  # type: ignore[assignment]

from src.core.domain.entities import Convocatoria, Delta, EventoCambio, Fuente
from src.core.domain.exceptions import RuleEngineError
from src.infra.logging import get_logger

logger = get_logger(__name__)


def _jaro_winkler_similarity(left: str, right: str) -> float:
    if jellyfish is not None:
        return jellyfish.jaro_winkler_similarity(left, right)
    return SequenceMatcher(None, left, right).ratio()


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

        matched_antiguas_ids: set[str] = set()
        unmatched_nuevas: list[Convocatoria] = []

        try:
            # Fase 1: Exact Matching por identificador_externo
            for nueva in nuevas_convocatorias:
                identificador = nueva.identificador_externo
                antigua = antiguas_convocatorias.get(identificador)

                if antigua and antigua.identificador_externo not in matched_antiguas_ids:
                    # Sincronizamos el ID para mantener integridad relacional
                    nueva.id = antigua.id
                    matched_antiguas_ids.add(antigua.identificador_externo)

                    # Si existe, comparamos campos
                    deltas = ChangeDetectorService._compare_fields(antigua, nueva, alertas_config.ignorar_cambios_en)

                    if deltas:
                        # Determinar relevancia basado en campos sensibles
                        es_relevante = any(d.campo in alertas_config.campos_sensibles for d in deltas)

                        evento = EventoCambio(
                            convocatoria_id=nueva.id,
                            identificador_externo=identificador,
                            tipo="MODIFICACION",
                            deltas=deltas,
                            es_relevante=es_relevante,
                        )
                        eventos.append(evento)
                else:
                    unmatched_nuevas.append(nueva)

            # Fase 2: Fuzzy Matching por título para las nuevas no emparejadas
            unmatched_antiguas = [
                a for a in antiguas_convocatorias.values() if a.identificador_externo not in matched_antiguas_ids
            ]

            FUZZY_THRESHOLD = 0.85

            for nueva in unmatched_nuevas:
                best_match = None
                best_score = 0.0

                if nueva.titulo:
                    nueva_titulo = str(nueva.titulo).lower()
                    for antigua in unmatched_antiguas:
                        if antigua.titulo:
                            score = _jaro_winkler_similarity(nueva_titulo, str(antigua.titulo).lower())
                            if score > best_score:
                                best_score = score
                                best_match = antigua

                if best_match and best_score >= FUZZY_THRESHOLD:
                    # Fuzzy match exitoso -> Es una modificación, el ID externo probablemente cambió
                    logger.info(
                        "Fuzzy match exitoso",
                        fuente_id=str(fuente.id),
                        score=round(best_score, 3),
                        titulo_nuevo=nueva.titulo,
                        titulo_antiguo=best_match.titulo,
                    )
                    unmatched_antiguas.remove(best_match)
                    matched_antiguas_ids.add(best_match.identificador_externo)

                    nueva.id = best_match.id
                    deltas = ChangeDetectorService._compare_fields(best_match, nueva, alertas_config.ignorar_cambios_en)

                    # Añadir un delta implícito para el identificador externo si cambió
                    if nueva.identificador_externo != best_match.identificador_externo:
                        deltas.append(
                            Delta(
                                campo="identificador_externo",
                                valor_anterior=best_match.identificador_externo,
                                valor_nuevo=nueva.identificador_externo,
                            )
                        )

                    if deltas:
                        es_relevante = any(d.campo in alertas_config.campos_sensibles for d in deltas)
                        eventos.append(
                            EventoCambio(
                                convocatoria_id=nueva.id,
                                identificador_externo=nueva.identificador_externo,
                                tipo="MODIFICACION",
                                deltas=deltas,
                                es_relevante=es_relevante,
                            )
                        )
                else:
                    # Si no hay match difuso, es realmente una APERTURA nueva
                    eventos.append(
                        EventoCambio(
                            convocatoria_id=nueva.id,
                            identificador_externo=nueva.identificador_externo,
                            tipo="APERTURA",
                            es_relevante=True,
                        )
                    )

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
