"""Tests para la registry dura de instituciones."""

from src.infra.sources.catalog import iter_source_profiles, resolve_source_profile


def test_resolve_source_profile_aliases() -> None:
    assert resolve_source_profile("CORFO").key == "CORFO"
    assert resolve_source_profile("CORFO_API").key == "CORFO"
    assert resolve_source_profile("CORFO_AJAX").key == "CORFO"
    assert resolve_source_profile("ANID_LLM").key == "ANID"


def test_registry_includes_expected_institutions() -> None:
    keys = {profile.key for profile in iter_source_profiles()}
    assert {
        "CORFO",
        "SERCOTEC",
        "FIA",
        "ANID",
        "INDAP",
        "FOSIS",
        "SUBDERE",
        "PROCHILE",
    }.issubset(keys)


def test_registry_excludes_removed_institutions() -> None:
    keys = {profile.key for profile in iter_source_profiles()}
    assert "ECONOMIA" not in keys
    assert "BANCOESTADO" not in keys


def test_fia_profile_exists() -> None:
    profile = resolve_source_profile("FIA")
    assert profile is not None
    assert profile.key == "FIA"
    assert len(profile.steps) >= 2


def test_corfo_primary_step_is_wp_ajax() -> None:
    profile = resolve_source_profile("CORFO")
    assert profile is not None
    assert profile.steps[0].fetcher == "wp_ajax"
    assert profile.steps[0].extractor == "wp_ajax"


def test_corfo_secondary_step_is_curl_cffi() -> None:
    profile = resolve_source_profile("CORFO")
    assert profile is not None
    assert len(profile.steps) >= 2
    assert profile.steps[1].fetcher == "curl_cffi"
    assert profile.steps[1].extractor == "html_static"


def test_sercotec_primary_step_is_json_api() -> None:
    profile = resolve_source_profile("SERCOTEC")
    assert profile is not None
    assert profile.steps[0].fetcher == "json_api"
    assert profile.steps[0].extractor == "json_api"


def test_anid_primary_step_is_rss_feed() -> None:
    profile = resolve_source_profile("ANID")
    assert profile is not None
    assert profile.steps[0].fetcher == "rss_feed"
    assert profile.steps[0].extractor == "rss_feed"


def test_fosis_primary_step_is_html_static() -> None:
    profile = resolve_source_profile("FOSIS")
    assert profile is not None
    assert profile.steps[0].fetcher == "html_static"


def test_fosis_secondary_step_is_curl_cffi() -> None:
    profile = resolve_source_profile("FOSIS")
    assert profile is not None
    assert len(profile.steps) >= 2
    assert profile.steps[1].fetcher == "curl_cffi"


def test_prochile_primary_step_is_curl_cffi() -> None:
    profile = resolve_source_profile("PROCHILE")
    assert profile is not None
    assert profile.steps[0].fetcher == "curl_cffi"


def test_corfo_ajax_alias() -> None:
    profile = resolve_source_profile("CORFO_AJAX")
    assert profile is not None
    assert profile.key == "CORFO"


def test_iter_source_profiles_returns_unique() -> None:
    profiles = iter_source_profiles()
    keys = [p.key for p in profiles]
    assert len(keys) == len(set(keys))
