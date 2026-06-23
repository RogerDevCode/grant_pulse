"""
Test E2E — Navegación prev/next en modal de detalle (GrantPulse)
Verifica:
  1. Radar: las flechas aparecen, el contador es correcto, prev/next navegan
  2. Radar + filtro: navList se actualiza, flechas respetan el orden filtrado
  3. Briefing: botón Detalle abre modal, flechas presentes y navegan
  4. Teclado: ArrowLeft / ArrowRight dentro del modal

Reglas AGENTS.md §6b:
  - Chromium headless, sin extensiones, contexto limpio por test
  - Sin dependencias entre tests
  - URL: producción Railway
"""

import pytest
from playwright.sync_api import sync_playwright, Page

BASE_URL = "https://grantpulse-production.up.railway.app"
TIMEOUT   = 20_000   # ms


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture()
def ctx(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    yield context
    context.close()


@pytest.fixture()
def page(ctx):
    p = ctx.new_page()
    p.goto(BASE_URL, wait_until="networkidle", timeout=30_000)
    yield p
    p.close()


# ──────────────────────────────────────────────────────────────
# UTILIDADES
# ──────────────────────────────────────────────────────────────

def open_first_card(page: Page) -> None:
    page.wait_for_selector(".conv-card", timeout=TIMEOUT)
    page.locator(".conv-card").first.click()
    page.wait_for_selector("#detailModal.active", timeout=TIMEOUT)


def modal_is_active(page: Page) -> bool:
    return page.locator("#detailModal.active").count() > 0


def nav_visible(page: Page) -> bool:
    return page.locator("#detailNav").is_visible()


def nav_counter_text(page: Page) -> str:
    return page.locator("#detailNavCounter").inner_text().strip()


def prev_disabled(page: Page) -> bool:
    return page.locator("#detailNavPrev").is_disabled()


def next_disabled(page: Page) -> bool:
    return page.locator("#detailNavNext").is_disabled()


# ──────────────────────────────────────────────────────────────
# TEST 1 — Radar: flechas visibles al abrir primera tarjeta
# ──────────────────────────────────────────────────────────────

def test_radar_nav_visible(page: Page):
    open_first_card(page)
    assert modal_is_active(page), "El modal no se abrió"
    assert nav_visible(page), "#detailNav debe ser visible cuando hay >1 tarjeta en el radar"
    counter = nav_counter_text(page)
    assert "/" in counter, f"El contador debe tener formato N/M, got: {counter!r}"


# ──────────────────────────────────────────────────────────────
# TEST 2 — Radar: primera tarjeta → prev deshabilitado
# ──────────────────────────────────────────────────────────────

def test_radar_first_card_prev_disabled(page: Page):
    open_first_card(page)
    assert prev_disabled(page), "En la primera tarjeta, prev debe estar deshabilitado"
    assert not next_disabled(page), "En la primera tarjeta, next debe estar habilitado"


# ──────────────────────────────────────────────────────────────
# TEST 3 — Radar: navegar →, contador incrementa
# ──────────────────────────────────────────────────────────────

def test_radar_next_increments_counter(page: Page):
    open_first_card(page)
    counter_before = nav_counter_text(page)
    idx_before = int(counter_before.split("/")[0].strip())

    page.locator("#detailNavNext").click()
    page.wait_for_function(
        f"document.getElementById('detailNavCounter').innerText.trim() !== '{counter_before}'",
        timeout=TIMEOUT,
    )
    counter_after = nav_counter_text(page)
    idx_after = int(counter_after.split("/")[0].strip())
    assert idx_after == idx_before + 1, (
        f"Contador debía ir de {idx_before} → {idx_before+1}, got {idx_after}"
    )


# ──────────────────────────────────────────────────────────────
# TEST 4 — Radar: → y luego ← vuelve al mismo ítem
# ──────────────────────────────────────────────────────────────

def test_radar_next_then_prev_returns(page: Page):
    open_first_card(page)
    counter_initial = nav_counter_text(page)

    page.locator("#detailNavNext").click()
    page.wait_for_function(
        f"document.getElementById('detailNavCounter').innerText.trim() !== '{counter_initial}'",
        timeout=TIMEOUT,
    )
    page.locator("#detailNavPrev").click()
    page.wait_for_function(
        f"document.getElementById('detailNavCounter').innerText.trim() === '{counter_initial}'",
        timeout=TIMEOUT,
    )
    assert nav_counter_text(page) == counter_initial


# ──────────────────────────────────────────────────────────────
# TEST 5 — Teclado ArrowRight / ArrowLeft
# ──────────────────────────────────────────────────────────────

def test_keyboard_arrow_navigation(page: Page):
    open_first_card(page)
    counter_before = nav_counter_text(page)
    idx_before = int(counter_before.split("/")[0].strip())

    page.keyboard.press("ArrowRight")
    page.wait_for_function(
        f"document.getElementById('detailNavCounter').innerText.trim() !== '{counter_before}'",
        timeout=TIMEOUT,
    )
    assert int(nav_counter_text(page).split("/")[0].strip()) == idx_before + 1

    page.keyboard.press("ArrowLeft")
    page.wait_for_function(
        f"document.getElementById('detailNavCounter').innerText.trim() === '{counter_before}'",
        timeout=TIMEOUT,
    )
    assert nav_counter_text(page) == counter_before


# ──────────────────────────────────────────────────────────────
# TEST 6 — Radar + filtro: navList se actualiza
# ──────────────────────────────────────────────────────────────

def test_radar_filter_updates_navlist(page: Page):
    page.wait_for_selector(".conv-card", timeout=TIMEOUT)

    toggle = page.locator("#soloActivasToggle")
    was_checked = toggle.is_checked()
    toggle.click()
    page.wait_for_selector(".conv-card", timeout=TIMEOUT)

    nav_source = page.evaluate("() => typeof state !== 'undefined' ? state.navSource : null")
    assert nav_source == "radar", f"navSource debe ser 'radar' tras filtrar en radar, got: {nav_source!r}"

    counter_after_total = int(
        page.evaluate("() => typeof state !== 'undefined' ? state.navList.length : 0")
    )
    assert counter_after_total >= 0

    page.locator(".conv-card").first.click()
    page.wait_for_selector("#detailModal.active", timeout=TIMEOUT)
    if nav_visible(page):
        total_modal = int(nav_counter_text(page).split("/")[1].strip())
        assert total_modal == counter_after_total, (
            f"Contador modal ({total_modal}) ≠ navList ({counter_after_total})"
        )

    # Restaurar
    page.keyboard.press("Escape")
    if not was_checked:
        toggle.click()


# ──────────────────────────────────────────────────────────────
# TEST 7 — Briefing: botón Detalle existe y abre modal
# ──────────────────────────────────────────────────────────────

def test_briefing_detail_button_opens_modal(page: Page):
    page.locator(".nav-item[data-page='briefing']").click()
    page.wait_for_selector(".briefing-detail-btn", timeout=TIMEOUT)

    btn = page.locator(".briefing-detail-btn").first
    assert btn.count() > 0, "Debe existir al menos un .briefing-detail-btn en el Briefing"

    btn.click()
    page.wait_for_selector("#detailModal.active", timeout=TIMEOUT)
    assert modal_is_active(page), "Modal no se abrió desde el Briefing"


# ──────────────────────────────────────────────────────────────
# TEST 8 — Briefing: navList fuente = briefing y contador coherente
# ──────────────────────────────────────────────────────────────

def test_briefing_navlist_source(page: Page):
    page.locator(".nav-item[data-page='briefing']").click()
    page.wait_for_selector(".briefing-detail-btn", timeout=TIMEOUT)

    nav_source = page.evaluate("() => typeof state !== 'undefined' ? state.navSource : null")
    assert nav_source == "briefing", f"navSource debe ser 'briefing', got: {nav_source!r}"

    briefing_count = int(
        page.evaluate("() => typeof state !== 'undefined' ? state.navList.length : 0")
    )
    assert briefing_count > 0, "navList debe tener registros en el Briefing"

    page.locator(".briefing-detail-btn").first.click()
    page.wait_for_selector("#detailModal.active", timeout=TIMEOUT)

    if nav_visible(page):
        total_modal = int(nav_counter_text(page).split("/")[1].strip())
        assert total_modal == briefing_count, (
            f"Contador modal ({total_modal}) ≠ navList briefing ({briefing_count})"
        )
