from src.grabador.parser import parsear, selector_desde_codigo

SCRIPT_BASICO = """import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://example.com/login")
    page.get_by_role("button", name="Entrar").click()
    page.get_by_text("Acepto los terminos").click()
    page.locator("#usuario").fill("admin@example.com")

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
"""

SCRIPT_FILTER_NTH = """from playwright.sync_api import Playwright, sync_playwright


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.locator("li.item").filter(has_text="Plan Pro").nth(2).click()

    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
"""

SCRIPT_NTH_SOBRE_ROLE = """from playwright.sync_api import Playwright, sync_playwright


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.get_by_role("cell", name="Idioma").nth(1).click()

    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
"""

SCRIPT_DBLCLICK_Y_PRESS = """from playwright.sync_api import Playwright, sync_playwright


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.get_by_role("heading", name="Example Domain").dblclick()
    page.get_by_role("textbox", name="Password").press("Enter")

    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
"""

SCRIPT_CON_HOVER_EN_MEDIO = """from playwright.sync_api import Playwright, sync_playwright


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://example.com/panel")
    page.get_by_role("link", name="Ver mas").hover()
    page.get_by_placeholder("Buscar").fill("factura 123")

    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
"""


def test_traduce_goto_get_by_role_get_by_text_y_locator_fill():
    elementos = parsear(SCRIPT_BASICO)

    assert elementos == [
        {"accion": "navegar", "url": "https://example.com/login"},
        {"accion": "clic", "selector": 'role=button[name="Entrar"]'},
        {"accion": "clic", "selector": 'text="Acepto los terminos"'},
        {"accion": "rellenar", "selector": "#usuario", "valor": "admin@example.com"},
    ]


def test_selector_desde_codigo_traduce_lo_que_muestra_el_inspector():
    assert (
        selector_desde_codigo('get_by_role("heading", name="Special-Use Domain Names")')
        == 'role=heading[name="Special-Use Domain Names"]'
    )
    assert selector_desde_codigo('page.get_by_text("Aceptar")') == 'text="Aceptar"'
    assert selector_desde_codigo("locator('.precio').nth(0)") == ".precio >> nth=0"


def test_selector_desde_codigo_devuelve_none_si_no_es_un_locator_valido():
    assert selector_desde_codigo(".precio") is None
    assert selector_desde_codigo("esto no es codigo valido !!") is None


def test_filter_y_nth_encadenados_producen_selector_playwright_no_css():
    elementos = parsear(SCRIPT_FILTER_NTH)

    assert len(elementos) == 1
    assert elementos[0]["accion"] == "clic"
    assert elementos[0]["selector"] == 'li.item:has-text("Plan Pro") >> nth=2'


def test_nth_sobre_selector_de_rol_usa_control_nth_no_css():
    elementos = parsear(SCRIPT_NTH_SOBRE_ROLE)

    assert len(elementos) == 1
    assert elementos[0]["accion"] == "clic"
    assert elementos[0]["selector"] == 'role=cell[name="Idioma"] >> nth=1'


def test_dblclick_marca_extraccion_y_press_marca_presionar():
    elementos = parsear(SCRIPT_DBLCLICK_Y_PRESS)

    assert elementos == [
        {"accion": "extraer", "selector": 'role=heading[name="Example Domain"]', "patron": None},
        {"accion": "presionar", "selector": 'role=textbox[name="Password"]', "valor": "Enter"},
    ]


def test_llamada_no_reconocida_conserva_su_posicion_en_el_orden():
    elementos = parsear(SCRIPT_CON_HOVER_EN_MEDIO)

    assert len(elementos) == 3
    assert elementos[0] == {"accion": "navegar", "url": "https://example.com/panel"}
    assert elementos[2] == {
        "accion": "rellenar",
        "selector": '[placeholder="Buscar"]',
        "valor": "factura 123",
    }

    entrada = elementos[1]
    assert entrada["no_reconocido"] is True
    assert "hover" in entrada["codigo"]
    assert "Ver mas" in entrada["codigo"]

    linea_esperada = next(
        i + 1 for i, linea in enumerate(SCRIPT_CON_HOVER_EN_MEDIO.splitlines()) if "hover" in linea
    )
    assert entrada["linea"] == linea_esperada
