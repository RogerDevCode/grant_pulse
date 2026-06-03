"""Registry canónico de instituciones y sus pipelines de scraping.

Las URLs de listado y los pasos de scraping se definen aquí para evitar
que queden distribuidos entre YAMLs y código de orquestación.

Jerarquía de scraping por paso:
1. Orgánico (json_api, wp_ajax, rss_feed) → datos estructurados sin WAF
2. curl_cffi (impersonación TLS) → HTML de sitios con WAF (BigIP, etc.)
3. html_static (httpx) → HTML de sitios sin protección
4. browser (Playwright) → JS rendering necesario
5. llm → último recurso para HTML muy ruidoso
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


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


# --- PERFILES POR INSTITUCIÓN ---

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
            note="admin-ajax.php con nonce dinámico. Estructurado y confiable.",
        ),
        ScrapeStep(
            fetcher="curl_cffi",
            extractor="html_static",
            url="https://www.corfo.gob.cl/sites/cpp/programasyconvocatorias/",
            note="Fallback: curl_cffi impersona Chrome120 para saltar BigIP WAF.",
        ),
    ),
    empty_state_markers=("No hay", "Sin resultados", "No se encontraron"),
)

_SERCOTEC = SourceProfile(
    key="SERCOTEC",
    root_url="https://www.sercotec.cl/",
    list_url="https://www.sercotec.cl/wp-json/wp/v2/programas",
    steps=(
        ScrapeStep(
            fetcher="json_api",
            extractor="json_api",
            url="https://www.sercotec.cl/wp-json/wp/v2/programas",
            note="REST API nativa de WordPress.",
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
    list_url="https://www.fia.cl/wp-json/wp/v2/convocatorias?per_page=50",
    steps=(
        ScrapeStep(
            fetcher="json_api",
            extractor="json_api",
            url="https://www.fia.cl/wp-json/wp/v2/convocatorias?per_page=50",
            note="REST API nativa de WordPress (CPT convocatorias, category=13).",
        ),
        ScrapeStep(
            fetcher="html_static",
            extractor="html_static",
            url="https://www.fia.cl/pilares-de-accion/impulso-para-innovar/convocatorias-y-licitaciones/",
            note="Fallback HTML estático (JS-rendered, menos confiable).",
        ),
    ),
    empty_state_markers=("No hay", "sin convocatorias", "No se encontraron"),
)

_ANID = SourceProfile(
    key="ANID",
    aliases=("ANID_LLM",),
    root_url="https://anid.cl/",
    list_url="https://anid.cl/concursos/",
    steps=(
        ScrapeStep(
            fetcher="rss_feed",
            extractor="rss_feed",
            url="https://anid.cl/feed/",
            note="RSS feed como canal orgánico primario (REST API devuelve 401).",
        ),
        ScrapeStep(
            fetcher="browser",
            extractor="html_static",
            url="https://anid.cl/concursos/",
            note="Fallback: JetEngine con carga asíncrona pesada.",
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
            note="Portal Drupal estable, sin WAF.",
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
            fetcher="html_static",
            extractor="html_static",
            url="https://www.fosis.gob.cl/es/programas/autonomia-economica/",
            note="Django CMS subpágina autonomía económica (10 programas).",
        ),
        ScrapeStep(
            fetcher="curl_cffi",
            extractor="html_static",
            url="https://www.fosis.gob.cl/es/programas/autonomia-economica/",
            note="Fallback curl_cffi si httpx recibe bloqueos.",
        ),
    ),
    empty_state_markers=("No hay", "sin programas", "No se encontraron"),
    note="TODO: agregar agregación multi-subpágina (autonomia-desarrollo/ tiene 11 programas más).",
)

_SUBDERE = SourceProfile(
    key="SUBDERE",
    root_url="https://www.subdere.gob.cl/",
    list_url="https://www.subdere.gob.cl/programas",
    steps=(
        ScrapeStep(
            fetcher="curl_cffi",
            extractor="html_static",
            url="https://www.subdere.gob.cl/programas",
            note="curl_cffi con impersonación Chrome para saltar WAF/403.",
        ),
        ScrapeStep(
            fetcher="browser",
            extractor="html_static",
            url="https://www.subdere.gob.cl/programas",
            note="Fallback Playwright si curl_cffi y httpx reciben 403.",
        ),
    ),
    empty_state_markers=("No hay", "sin programas", "No se encontraron"),
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
            note="ASP.NET con TLS fingerprinting. curl_cffi con impersonación Chrome obtiene HTML renderizado.",
        ),
        ScrapeStep(
            fetcher="browser",
            extractor="html_static",
            url="https://www.prochile.gob.cl/herramientas/concursos/",
            note="Fallback browser si curl_cffi no obtiene contenido.",
        ),
    ),
    empty_state_markers=("No hay", "sin concursos", "No se encontraron"),
    note="ASP.NET con documentos PDF por sector/año. Sin estado ni fecha en listing.",
)


# --- REGISTRY ---

_PROFILES: dict[str, SourceProfile] = {}

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
    _PROFILES[_normalize_name(profile.key)] = profile
    for alias in profile.aliases:
        _PROFILES[_normalize_name(alias)] = profile


def resolve_source_profile(source_name: str) -> SourceProfile | None:
    """Retorna el perfil canónico para una fuente conocida."""
    return _PROFILES.get(_normalize_name(source_name))


def iter_source_profiles() -> tuple[SourceProfile, ...]:
    """Itera sobre los perfiles canónicos únicos."""
    seen: set[str] = set()
    ordered: list[SourceProfile] = []
    for profile in _PROFILES.values():
        if profile.key in seen:
            continue
        seen.add(profile.key)
        ordered.append(profile)
    return tuple(ordered)
