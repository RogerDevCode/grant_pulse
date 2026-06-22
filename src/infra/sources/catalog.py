"""Registry canónico de instituciones y sus pipelines de scraping.

Las fuentes se registran desde tres orígenes en orden de precedencia:
1. YAML rules/ → dinámico, sin tocar código (primario)
2. Registro en código → perfiles hardcodeados (fallback para fuentes sin YAML)
3. Base de datos → perfiles registrados vía API

Agregar una nueva fuente = crear un nuevo archivo .yaml en rules/. No requiere código.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.infra.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class ScrapeStep:
    fetcher: str
    extractor: str
    url: str
    note: str = ""


@dataclass(slots=True)
class SourceProfile:
    key: str
    root_url: str
    list_url: str
    steps: tuple[ScrapeStep, ...]
    aliases: tuple[str, ...] = field(default_factory=tuple)
    empty_state_markers: tuple[str, ...] = field(default_factory=tuple)
    min_request_interval_seconds: float = 2.0
    max_llm_context_chars: int = 100_000
    note: str = ""


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


# ─── YAML DYNAMIC REGISTRY ──────────────────────────────────────────

_RULES_DIR = Path(__file__).parent.parent.parent.parent / "rules"

# Mapa de estrategias YAML → (fetcher, extractor) por defecto
_STRATEGY_MAP: dict[str, tuple[str, str]] = {
    "html_static": ("html_static", "html_static"),
    "json_api": ("json_api", "json_api"),
    "wp_ajax": ("wp_ajax", "wp_ajax"),
    "rss_feed": ("rss_feed", "rss_feed"),
    "curl_cffi": ("curl_cffi", "html_static"),
    "browser": ("browser", "html_static"),
    "llm": ("html_static", "llm"),
    "fosis_multipage": ("fosis_multipage", "fosis_multipage"),
    "subdere_homepage": ("subdere_homepage", "subdere_homepage"),
}


def _build_profile_from_yaml(filepath: Path) -> SourceProfile | None:
    """Construye un SourceProfile a partir de un archivo YAML de reglas."""
    try:
        with open(filepath) as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        logger.warning(f"Error leyendo YAML {filepath.name}: {e}")
        return None

    nombre = data.get("nombre") or filepath.stem
    url_busqueda = data.get("url_busqueda", "")
    estrategia = data.get("estrategia", "html_static")
    url_base = data.get("url_base", url_busqueda)

    if not url_busqueda:
        return None

    # Estrategia principal
    fetcher, extractor = _STRATEGY_MAP.get(estrategia, ("html_static", "html_static"))

    steps: list[ScrapeStep] = [
        ScrapeStep(fetcher=fetcher, extractor=extractor, url=url_busqueda, note=f"Primario: {estrategia}"),
    ]

    # Pasos de fallback desde YAML (opcional)
    fallback_steps: list[dict[str, str]] = data.get("fallback_steps") or []
    for fb in fallback_steps:
        fb_fetcher, fb_extractor = _STRATEGY_MAP.get(
            fb.get("estrategia", "html_static"), ("html_static", "html_static")
        )
        steps.append(
            ScrapeStep(
                fetcher=fb_fetcher,
                extractor=fb_extractor,
                url=fb.get("url", url_busqueda),
                note=fb.get("nota", f"Fallback: {fb.get('estrategia', 'html_static')}"),
            )
        )

    # Aliases desde YAML
    aliases: list[str] = data.get("aliases") or []

    return SourceProfile(
        key=nombre,
        root_url=url_base,
        list_url=url_busqueda,
        steps=tuple(steps),
        aliases=tuple(aliases),
        empty_state_markers=("No hay", "Sin resultados", "No se encontraron"),
        note=data.get("descripcion", f"Fuente {nombre} registrada desde {filepath.name}"),
    )


def _load_yaml_profiles() -> dict[str, SourceProfile]:
    """Escanea rules/ y construye perfiles dinámicos."""
    profiles: dict[str, SourceProfile] = {}
    rules_dir = _RULES_DIR

    if not rules_dir.is_dir():
        logger.warning(f"Directorio de reglas no encontrado: {rules_dir}")
        return profiles

    for yaml_file in sorted(rules_dir.glob("*.yaml")):
        profile = _build_profile_from_yaml(yaml_file)
        if profile is None:
            continue
        key = _normalize_name(profile.key)
        profiles[key] = profile
        for alias in profile.aliases:
            profiles[_normalize_name(alias)] = profile

    logger.info(f"Perfiles cargados desde YAML: {len({p.key for p in profiles.values()})} fuentes")
    return profiles


# ─── HARDCODED FALLBACK PROFILES ──────────────────────────────────

_CORFO = SourceProfile(
    key="CORFO",
    aliases=("CORFO_API", "CORFO_AJAX"),
    root_url="https://www.corfo.gob.cl/",
    list_url="https://www.corfo.gob.cl/sites/cpp/programasyconvocatorias/",
    steps=(
        ScrapeStep(
            fetcher="wp_ajax",
            extractor="wp_ajax",
            url="https://www.corfo.gob.cl/sites/cpp/programasyconvocatorias/",
            note="admin-ajax.php con nonce dinámico.",
        ),
        ScrapeStep(
            fetcher="curl_cffi",
            extractor="html_static",
            url="https://www.corfo.gob.cl/sites/cpp/programasyconvocatorias/",
            note="Fallback: curl_cffi para BigIP WAF.",
        ),
    ),
    empty_state_markers=("No hay", "Sin resultados", "No se encontraron"),
)

_SERCOTEC = SourceProfile(
    key="SERCOTEC",
    root_url="https://www.sercotec.cl/",
    list_url="https://apisctwidgets.sercotec.cl/api/convocatorias?idRegion=0&idTipoInstrumento=0&idEtapa=0&pagina=1&cantidad=500",
    steps=(
        ScrapeStep(
            fetcher="json_api",
            extractor="json_api",
            url="https://apisctwidgets.sercotec.cl/api/convocatorias?idRegion=0&idTipoInstrumento=0&idEtapa=0&pagina=1&cantidad=500",
            note="Widget API oficial con cantidad=500.",
        ),
        ScrapeStep(
            fetcher="html_static",
            extractor="html_static",
            url="https://www.sercotec.cl/convocatorias-regionales-2024/",
            note="Fallback HTML estático.",
        ),
    ),
    empty_state_markers=("No hay", "sin resultados", "No se encontraron"),
)

_FIA = SourceProfile(
    key="FIA",
    root_url="https://www.fia.cl/",
    list_url="https://www.fia.cl/wp-json/wp/v2/convocatorias?per_page=100",
    steps=(
        ScrapeStep(
            fetcher="json_api",
            extractor="json_api",
            url="https://www.fia.cl/wp-json/wp/v2/convocatorias?per_page=100",
            note="REST API nativa de WordPress.",
        ),
        ScrapeStep(
            fetcher="html_static",
            extractor="html_static",
            url="https://www.fia.cl/pilares-de-accion/impulso-para-innovar/convocatorias-y-licitaciones/",
            note="Fallback HTML estático.",
        ),
    ),
    empty_state_markers=("No hay", "sin convocatorias", "No se encontraron"),
)

_ANID = SourceProfile(
    key="ANID",
    root_url="https://anid.cl/",
    list_url="https://anid.cl/concursos/",
    aliases=("ANID_LLM",),
    steps=(
        ScrapeStep(
            fetcher="rss_feed",
            extractor="rss_feed",
            url="https://anid.cl/feed/",
            note="RSS feed primario.",
        ),
        ScrapeStep(
            fetcher="browser",
            extractor="html_static",
            url="https://anid.cl/concursos/",
            note="Fallback browser.",
        ),
    ),
    empty_state_markers=("No hay", "sin resultados", "No se encontraron"),
)

_INDAP = SourceProfile(
    key="INDAP",
    root_url="https://www.indap.gob.cl/",
    list_url="https://www.indap.gob.cl/plataforma-de-servicios/",
    steps=(
        ScrapeStep(
            fetcher="html_static",
            extractor="html_static",
            url="https://www.indap.gob.cl/plataforma-de-servicios/",
            note="Portal Drupal estable.",
        ),
    ),
    empty_state_markers=("No hay", "sin resultados", "No se encontraron"),
)

_FOSIS = SourceProfile(
    key="FOSIS",
    root_url="https://www.fosis.gob.cl/",
    list_url="https://www.fosis.gob.cl/es/programas/autonomia-economica/",
    steps=(
        ScrapeStep(
            fetcher="fosis_multipage",
            extractor="fosis_multipage",
            url="https://www.fosis.gob.cl/es/programas/autonomia-economica/",
            note="Multi-subpágina: ~30+ items.",
        ),
    ),
    empty_state_markers=("No hay", "sin programas", "No se encontraron"),
)

_SUBDERE = SourceProfile(
    key="SUBDERE",
    root_url="https://www.subdere.gob.cl/",
    list_url="https://www.subdere.gob.cl/",
    steps=(
        ScrapeStep(
            fetcher="subdere_homepage",
            extractor="subdere_homepage",
            url="https://www.subdere.gob.cl/",
            note="Homepage scraping, WAF bloquea rutas internas.",
        ),
    ),
    empty_state_markers=("No hay", "sin programas", "No se encontraron"),
    note="Solo homepage (/) retorna 200.",
)

_PROCHILE = SourceProfile(
    key="PROCHILE",
    root_url="https://www.prochile.gob.cl/",
    list_url="https://www.prochile.gob.cl/herramientas/concursos/",
    steps=(
        ScrapeStep(
            fetcher="curl_cffi",
            extractor="html_static",
            url="https://www.prochile.gob.cl/herramientas/concursos/",
            note="curl_cffi impersona Chrome para ASP.NET.",
        ),
        ScrapeStep(
            fetcher="browser",
            extractor="html_static",
            url="https://www.prochile.gob.cl/herramientas/concursos/",
            note="Fallback browser.",
        ),
    ),
    empty_state_markers=("No hay", "sin concursos", "No se encontraron"),
)


_HARDCODED: dict[str, SourceProfile] = {}

for profile in (
    _CORFO,
    _SERCOTEC,
    _FIA,
    _ANID,
    _INDAP,
    _FOSIS,
    _SUBDERE,
    _PROCHILE,
):
    _HARDCODED[_normalize_name(profile.key)] = profile
    for alias in profile.aliases:
        _HARDCODED[_normalize_name(alias)] = profile


# ─── CACHE DE PERFILES YAML ────────────────────────────────────────

_yaml_cache: dict[str, SourceProfile] | None = None


def _get_yaml_profiles() -> dict[str, SourceProfile]:
    """Retorna perfiles YAML cacheados (se recarga en cada import en dev)."""
    global _yaml_cache
    if _yaml_cache is None:
        _yaml_cache = _load_yaml_profiles()
    return _yaml_cache


# ─── API PÚBLICA ───────────────────────────────────────────────────


def resolve_source_profile(source_name: str) -> SourceProfile | None:
    """
    Retorna el perfil canónico para una fuente.

    Precedencia:
    1. Hardcoded catalog (perfiles con pipeline steps completos y probados)
    2. YAML rules/ (perfiles dinámicos para fuentes sin perfil hardcodeado)

    Esto permite agregar nuevas fuentes simplemente creando un YAML en rules/,
    sin tocar código. Las fuentes conocidas mantienen sus pipelines probados.
    """
    key = _normalize_name(source_name)

    # 1. Hardcoded (perfiles con pipeline steps completos)
    profile = _HARDCODED.get(key)
    if profile is not None:
        return profile

    # 2. YAML dinámico (para fuentes sin perfil hardcodeado)
    return _get_yaml_profiles().get(key)


def iter_source_profiles() -> tuple[SourceProfile, ...]:
    """Itera sobre todos los perfiles disponibles (YAML + hardcoded)."""
    seen: set[str] = set()
    ordered: list[SourceProfile] = []

    # YAML primero
    for profile in _get_yaml_profiles().values():
        if profile.key in seen:
            continue
        seen.add(profile.key)
        ordered.append(profile)

    # Hardcoded después (solo los que no estén ya cubiertos por YAML)
    for profile in _HARDCODED.values():
        if profile.key in seen:
            continue
        seen.add(profile.key)
        ordered.append(profile)

    return tuple(ordered)


def register_yaml_profile(filepath: str | Path) -> SourceProfile | None:
    """Registra un perfil desde un archivo YAML en tiempo de ejecución.
    Útil para agregar fuentes sin reiniciar la aplicación.
    """
    global _yaml_cache
    path = Path(filepath) if isinstance(filepath, str) else filepath
    profile = _build_profile_from_yaml(path)
    if profile is None:
        return None
    if _yaml_cache is None:
        _yaml_cache = {}
    key = _normalize_name(profile.key)
    _yaml_cache[key] = profile
    for alias in profile.aliases:
        _yaml_cache[_normalize_name(alias)] = profile
    logger.info("Perfil registrado dinámicamente", path=path.name)
    return profile


def invalidate_yaml_cache() -> None:
    """Invalida el cache de perfiles YAML para forzar recarga."""
    global _yaml_cache
    _yaml_cache = None
