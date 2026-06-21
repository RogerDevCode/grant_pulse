"""
Módulo encargado de normalizar datos crudos extraídos y mapearlos a entidades de dominio.
"""

import asyncio
import html
import json
import re
import threading
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

from src.core.domain.entities import Convocatoria, Fuente
from src.core.domain.estado_normalizer import normalize_estado
from src.core.domain.exceptions import NormalizationError
from src.core.domain.fecha_utils import parse_fecha_chilena
from src.infra.config import settings
from src.infra.llm.client import build_llm_client
from src.infra.logging import get_logger

logger = get_logger(__name__)

REGIONES_CHILE: tuple[str, ...] = (
    "Arica y Parinacota",
    "Tarapacá",
    "Antofagasta",
    "Atacama",
    "Coquimbo",
    "Valparaíso",
    "Metropolitana",
    "O'Higgins",
    "Maule",
    "Ñuble",
    "Biobío",
    "La Araucanía",
    "Los Ríos",
    "Los Lagos",
    "Aysén del General Carlos Ibáñez del Campo",
    "Magallanes y de la Antártica Chilena",
    "Nacional",
)


_REGION_ALIASES: dict[str, str] = {
    "araucania": "La Araucanía",
    "araucanía": "La Araucanía",
    "bio bio": "Biobío",
    "biobío": "Biobío",
    "metropolitana": "Metropolitana",
    "santiago": "Metropolitana",
    "valparaiso": "Valparaíso",
    "valparaíso": "Valparaíso",
    "ohiggins": "O'Higgins",
    "o higgins": "O'Higgins",
    "maule": "Maule",
    "uble": "Ñuble",
    "los rios": "Los Ríos",
    "los ríos": "Los Ríos",
    "rios": "Los Ríos",
    "los lagos": "Los Lagos",
    "lagos": "Los Lagos",
    "aysen": "Aysén del General Carlos Ibáñez del Campo",
    "aysén": "Aysén del General Carlos Ibáñez del Campo",
    "magallanes": "Magallanes y de la Antártica Chilena",
    "antartica": "Magallanes y de la Antártica Chilena",
    "antártica": "Magallanes y de la Antártica Chilena",
    "tarapaca": "Tarapacá",
    "tarapacá": "Tarapacá",
    "antofagasta": "Antofagasta",
    "atacama": "Atacama",
    "coquimbo": "Coquimbo",
    "arica": "Arica y Parinacota",
    "parinacota": "Arica y Parinacota",
}


def _coerce_region(text: str | None) -> str | None:
    if not text or not isinstance(text, str):
        return None
    value = text.strip()
    if not value:
        return None
    lowered = value.lower()
    for r in REGIONES_CHILE:
        if lowered == r.lower():
            return r
    normalized = (
        lowered.replace("-", " ")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    normalized = " ".join(normalized.split())
    for alias, canonical in _REGION_ALIASES.items():
        alias_norm = alias.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
        if alias_norm == normalized or alias_norm in normalized:
            return canonical
    for r in REGIONES_CHILE:
        r_norm = r.lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
        if r_norm == normalized or r_norm in normalized:
            return r
    return None


def _run_async_in_thread(coro: Coroutine[Any, Any, Any]) -> Any:
    """Ejecuta una coroutine en un hilo separado para soportar inferencia LLM desde código síncrono."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: Any = None
    error: Exception | None = None

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
                return _coerce_region(region.strip())

    match = re.search(r'"region"\s*:\s*"([^"]+)"', cleaned)
    if match:
        return _coerce_region(match.group(1).strip())

    return None


def _infer_region_with_llm(titulo: str | None, descripcion: str | None, url_detalle: str | None, fuente: Fuente) -> str | None:
    """Intenta inferir la región de una convocatoria usando LLM si no viene explícita en los datos crudos."""

    if not titulo and not descripcion and not url_detalle:
        return None

    if not (settings.OPENROUTER_API_KEY or settings.LLM_API_KEY or settings.GROQ_API_KEY or settings.NVIDIA_API_KEY):
        logger.info("No hay API key LLM configurada; se omite inferencia de región", fuente=fuente.nombre)
        return None

    opciones = ", ".join(REGIONES_CHILE)
    prompt = (
        "Eres un clasificador geográfico para convocatorias chilenas. "
        "Responde SOLO con JSON válido con la clave 'region'. "
        "Elige UNA región desde esta lista exacta: "
        f"{opciones}.\n\n"
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


def _extract_int(text: str, field_name: str) -> int:
    """Convierte un string numérico limpio a int."""
    try:
        limpio = text.replace(".", "").replace(",", "")
        return int(limpio)
    except ValueError as e:
        msg = f"Fallo al parsear entero '{text}' para el campo '{field_name}'"
        logger.error(msg, exc=e)
        raise NormalizationError(msg) from e


def _clean_text(s: str) -> str:
    """Limpia tags HTML y normaliza espacios."""
    if not s:
        return s
    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^\s*(?:Convocatoria|Bases?)\s+", "", s, flags=re.I)
    return s


def _extract_canonico(text: str, regex_pattern: str, mapping: dict[str, str], field_name: str) -> str:
    """Extrae con regex y luego aplica un mapeo canónico."""
    extracted = _apply_regex(text, regex_pattern, field_name)
    lowered = extracted.lower()
    for key, canonical in mapping.items():
        if key in lowered:
            return canonical
    return extracted.capitalize()


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
            raw_titulo = item.get("titulo")
            estado = item.get("estado")

            if not identificador:
                logger.warning("Item carece de identificador, saltando", fuente=fuente.nombre)
                skipped += 1
                continue
            if not raw_titulo:
                logger.warning("Item carece de titulo, saltando", identificador=identificador, fuente=fuente.nombre)
                skipped += 1
                continue

            titulo = _clean_text(raw_titulo)
            descripcion = _clean_text(item.get("descripcion") or "") or None
            estado = normalize_estado(estado)

            url_final: str | None = None
            if url_detalle:
                url_final = (
                    str(fuente.url_base).rstrip("/") + "/" + url_detalle.lstrip("/")
                    if url_detalle.startswith("/")
                    else url_detalle
                )

            fecha_apertura_val: datetime | None = None
            fecha_cierre_val: datetime | None = None
            monto_val: float | None = None
            metadatos: dict[str, str | int | float | bool | None] = {}
            skip_item = False

            try:
                raw_fecha_apertura = item.get("fecha_apertura")
                if raw_fecha_apertura and norm_config.fecha_apertura:
                    texto_fecha = raw_fecha_apertura
                    if norm_config.fecha_apertura.regex_extraction:
                        texto_fecha = _apply_regex(
                            texto_fecha, norm_config.fecha_apertura.regex_extraction, "fecha_apertura"
                        )
                    if norm_config.fecha_apertura.formato_salida:
                        fecha_apertura_val = _parse_date(
                            texto_fecha, norm_config.fecha_apertura.formato_salida, "fecha_apertura"
                        )
                elif raw_fecha_apertura:
                    fecha_apertura_val = parse_fecha_chilena(raw_fecha_apertura)
            except NormalizationError as e:
                logger.warning("Campo fecha_apertura omitido por error de normalización", item_id=identificador, exc=e)

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
            except NormalizationError as e:
                logger.warning("Campo fecha_cierre omitido por error de normalización", item_id=identificador, exc=e)

            try:
                raw_monto = item.get("monto")
                if raw_monto and norm_config.monto:
                    texto_monto = raw_monto
                    if norm_config.monto.regex_extraction:
                        texto_monto = _apply_regex(texto_monto, norm_config.monto.regex_extraction, "monto")
                    monto_val = _parse_float(texto_monto, "monto")
            except NormalizationError as e:
                logger.warning("Campo monto omitido por error de normalización", item_id=identificador, exc=e)

            # Extraer nuevos campos hacia metadatos
            for extra_field in ["cupo", "porcentaje_cofinanciamiento", "plazo_ejecucion_meses", "tipo_beneficiario", "instrumento", "area_financiamiento"]:
                try:
                    conf = getattr(norm_config, extra_field, None)
                    raw_val = item.get(extra_field) or item.get("descripcion") or item.get("titulo") # Fallback to raw text
                    if conf and conf.regex_extraction and raw_val:
                        if conf.tipo_dato == "int":
                            extracted = _apply_regex(raw_val, conf.regex_extraction, extra_field)
                            metadatos[extra_field] = _extract_int(extracted, extra_field)
                        elif conf.tipo_dato == "float":
                            extracted = _apply_regex(raw_val, conf.regex_extraction, extra_field)
                            metadatos[extra_field] = _parse_float(extracted, extra_field)
                        elif conf.tipo_dato == "mapeo_canonico" and conf.mapeo_canonico:
                            metadatos[extra_field] = _extract_canonico(raw_val, conf.regex_extraction, conf.mapeo_canonico, extra_field)
                        else:
                            metadatos[extra_field] = _apply_regex(raw_val, conf.regex_extraction, extra_field)
                except NormalizationError as e:
                    logger.debug(f"Campo {extra_field} omitido por error de normalización", item_id=identificador, exc=e)

            # Plazo de postulación automático
            if fecha_apertura_val and fecha_cierre_val and fecha_cierre_val > fecha_apertura_val:
                metadatos["plazo_postulacion_dias"] = (fecha_cierre_val - fecha_apertura_val).days

            if skip_item:
                skipped += 1
                continue

            if estado == "DESCONOCIDO" and fecha_cierre_val is not None and fecha_cierre_val >= now:
                estado = "ABIERTO"

            region = item.get("region")
            if not region and fuente.configuracion_reglas.region_defecto:
                region = fuente.configuracion_reglas.region_defecto
            if not region:
                region = _infer_region_with_llm(titulo, descripcion, url_final, fuente)

            convocatoria = Convocatoria(
                fuente_id=fuente.id, # type: ignore
                identificador_externo=identificador,
                titulo=titulo,
                descripcion=descripcion,
                url_detalle=url_final, # type: ignore
                fecha_apertura=fecha_apertura_val,
                fecha_cierre=fecha_cierre_val,
                monto=monto_val,
                region=region,
                estado=estado,
                metadatos=metadatos,
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
