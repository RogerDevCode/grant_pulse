"""
Módulo encargado de normalizar datos crudos extraídos y mapearlos a entidades de dominio.
"""

import asyncio
import json
import re
import threading
from datetime import UTC, datetime

from src.core.domain.entities import Convocatoria, Fuente
from src.core.domain.estado_normalizer import normalize_estado
from src.core.domain.exceptions import NormalizationError
from src.core.domain.fecha_utils import parse_fecha_chilena
from src.infra.config import settings
from src.infra.llm.client import build_llm_client
from src.infra.logging import get_logger

logger = get_logger(__name__)


def _run_async_in_thread(coro):
    """Ejecuta una coroutine en un hilo separado para soportar inferencia LLM desde código síncrono."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result = None
    error = None

    def runner() -> None:
        nonlocal result, error
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(coro)
        except Exception as exc:  # noqa: BLE001
            error = exc
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()

    if error is not None:
        raise error
    return result


def _extract_region_from_response(response_text: str) -> str | None:
    """Extrae una región desde una respuesta LLM robusta a ruido en JSON."""

    cleaned = response_text.strip()

    for candidate in (cleaned, cleaned.removeprefix("```json").removesuffix("```")):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        if isinstance(parsed, dict):
            region = parsed.get("region") or parsed.get("nombre_region") or parsed.get("región")
            if isinstance(region, str) and region.strip():
                return region.strip()

    match = re.search(r'"region"\s*:\s*"([^"]+)"', cleaned)
    if match:
        return match.group(1).strip()

    return None


def _infer_region_with_llm(titulo: str | None, descripcion: str | None, url_detalle: str | None, fuente: Fuente) -> str | None:
    """Intenta inferir la región de una convocatoria usando LLM si no viene explícita en los datos crudos."""

    if not titulo and not descripcion and not url_detalle:
        return None

    if not (settings.OPENROUTER_API_KEY or settings.LLM_API_KEY or settings.GROQ_API_KEY or settings.NVIDIA_API_KEY):
        logger.info("No hay API key LLM configurada; se omite inferencia de región", fuente=fuente.nombre)
        return None

    prompt = (
        "Eres un clasificador geográfico para convocatorias chilenas. "
        "Responde SOLO con JSON válido con la clave 'region'. "
        "Usa una sola región de Chile (por ejemplo: Metropolitana, Valparaíso, Biobío, Ñuble, etc.). "
        "Si no puedes inferir una región clara, devuelve 'Nacional'.\n\n"
        f"Fuente: {fuente.nombre}\n"
        f"Título: {titulo or 'Sin título'}\n"
        f"Descripción: {descripcion or 'Sin descripción'}\n"
        f"URL: {url_detalle or 'Sin URL'}"
    )

    try:
        client = build_llm_client()

        async def _ask() -> str:
            return await client.chat_completion(prompt, system_prompt="Eres un asistente experto en geografía chilena.", timeout=45)

        response_text = _run_async_in_thread(_ask())
        inferred = _extract_region_from_response(response_text)
        if inferred:
            logger.info("Región inferida por LLM", fuente=fuente.nombre, region=inferred)
            return inferred
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fallo al inferir región con LLM", fuente=fuente.nombre, exc=exc)

    return None


def _apply_regex(text: str, regex_pattern: str, field_name: str) -> str:
    """Aplica una expresión regular a un texto y extrae el primer grupo o el match completo."""
    try:
        match = re.search(regex_pattern, text)
        if not match:
            raise NormalizationError(
                f"El texto '{text}' no coincide con la regex '{regex_pattern}' para el campo '{field_name}'"
            )

        if match.groups():
            return match.group(1).strip()
        return match.group(0).strip()
    except re.error as e:
        msg = f"Expresión regular inválida '{regex_pattern}' para el campo '{field_name}': {e}"
        logger.error(msg, exc=e)
        raise NormalizationError(msg) from e


def _parse_date(date_str: str, date_format: str, field_name: str) -> datetime:
    """Parsea un string a datetime usando un formato específico, con soporte básico para meses en español."""
    try:
        meses = {
            "enero": "January",
            "febrero": "February",
            "marzo": "March",
            "abril": "April",
            "mayo": "May",
            "junio": "June",
            "julio": "July",
            "agosto": "August",
            "septiembre": "September",
            "octubre": "October",
            "noviembre": "November",
            "diciembre": "December",
        }

        texto_procesado = date_str.lower()
        for es, en in meses.items():
            if es in texto_procesado:
                texto_procesado = texto_procesado.replace(es, en)
                break

        parsed = datetime.strptime(texto_procesado, date_format)
        return parsed.replace(tzinfo=UTC)
    except ValueError as e:
        msg = f"Fallo al parsear fecha '{date_str}' con formato '{date_format}' para el campo '{field_name}'"
        logger.error(msg, exc=e)
        raise NormalizationError(msg) from e


def _parse_float(monto_str: str, field_name: str) -> float:
    """Convierte un string numérico limpio a float."""
    try:
        limpio = monto_str.replace(".", "").replace(",", ".")
        return float(limpio)
    except ValueError as e:
        msg = f"Fallo al parsear monto '{monto_str}' a float para el campo '{field_name}'"
        logger.error(msg, exc=e)
        raise NormalizationError(msg) from e


class DataNormalizer:
    """
    Toma diccionarios de strings crudos desde los scrapers, aplica
    reglas de limpieza y formatea los datos a entidades Convocatoria.
    """

    @staticmethod
    def normalize_and_map(raw_items: list[dict[str, str | None]], fuente: Fuente) -> list[Convocatoria]:
        logger.info("Iniciando normalización de items", total_items=len(raw_items), fuente_id=str(fuente.id))

        norm_config = fuente.configuracion_reglas.normalizadores
        convocatorias: list[Convocatoria] = []
        skipped = 0

        now = datetime.now(UTC)
        for item in raw_items:
            identificador = item.get("identificador")
            url_detalle = item.get("url_detalle")
            titulo = item.get("titulo")
            estado = item.get("estado")

            if not identificador:
                logger.warning("Item carece de identificador, saltando", fuente=fuente.nombre)
                skipped += 1
                continue
            if not titulo:
                logger.warning("Item carece de titulo, saltando", identificador=identificador, fuente=fuente.nombre)
                skipped += 1
                continue
            if not url_detalle:
                logger.warning(
                    "Item carece de url_detalle, saltando",
                    identificador=identificador,
                    titulo=titulo,
                    fuente=fuente.nombre,
                )
                skipped += 1
                continue

            estado = normalize_estado(estado)

            url_final = (
                str(fuente.url_base).rstrip("/") + "/" + url_detalle.lstrip("/")
                if url_detalle.startswith("/")
                else url_detalle
            )

            fecha_cierre_val: datetime | None = None
            monto_val: float | None = None
            skip_item = False

            try:
                raw_fecha_cierre = item.get("fecha_cierre")
                if raw_fecha_cierre and norm_config.fecha_cierre:
                    texto_fecha = raw_fecha_cierre
                    if norm_config.fecha_cierre.regex_extraction:
                        texto_fecha = _apply_regex(
                            texto_fecha, norm_config.fecha_cierre.regex_extraction, "fecha_cierre"
                        )

                    if norm_config.fecha_cierre.formato_salida:
                        fecha_cierre_val = _parse_date(
                            texto_fecha, norm_config.fecha_cierre.formato_salida, "fecha_cierre"
                        )
                    else:
                        logger.warning(
                            "fecha_cierre extraída pero sin formato_salida definido.",
                            item_id=identificador,
                        )
                elif raw_fecha_cierre:
                    fecha_cierre_val = parse_fecha_chilena(raw_fecha_cierre)
                    if not fecha_cierre_val:
                        logger.debug(
                            "fecha_cierre presente pero no reconocida por parse_fecha_chilena",
                            item_id=identificador,
                            raw=raw_fecha_cierre,
                        )

                if fecha_cierre_val and fecha_cierre_val < now:
                    logger.info(
                        "Filtrando convocatoria expirada",
                        titulo=titulo,
                        fecha_cierre=fecha_cierre_val.isoformat(),
                    )
                    skip_item = True

                raw_monto = item.get("monto")
                if raw_monto and norm_config.monto:
                    texto_monto = raw_monto
                    if norm_config.monto.regex_extraction:
                        texto_monto = _apply_regex(texto_monto, norm_config.monto.regex_extraction, "monto")
                    monto_val = _parse_float(texto_monto, "monto")
            except NormalizationError as e:
                msg = f"Fallo al normalizar item {identificador} de la fuente {fuente.nombre}: {e}"
                logger.warning(msg, exc=e)
                skip_item = True

            if skip_item:
                skipped += 1
                continue

            if estado == "DESCONOCIDO" and fecha_cierre_val is not None and fecha_cierre_val >= now:
                estado = "ABIERTO"

            region = item.get("region")
            if not region and fuente.configuracion_reglas.region_defecto:
                region = fuente.configuracion_reglas.region_defecto
            if not region:
                region = _infer_region_with_llm(titulo, item.get("descripcion"), url_final, fuente)

            convocatoria = Convocatoria(
                fuente_id=fuente.id,
                identificador_externo=identificador,
                titulo=titulo,
                descripcion=item.get("descripcion"),
                url_detalle=url_final,  # type: ignore
                fecha_cierre=fecha_cierre_val,
                monto=monto_val,
                region=region,
                estado=estado,
            )
            convocatorias.append(convocatoria)

        if skipped > 0:
            logger.info(
                "Normalización completada con items saltados",
                total=len(raw_items),
                ok=len(convocatorias),
                skipped=skipped,
                fuente=fuente.nombre,
            )

        return convocatorias
