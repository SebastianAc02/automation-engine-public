from unittest.mock import MagicMock

from src.ejecutores.camoufox import CamoufoxEjecutor
from src.models import Receta


def _mockear_camoufox(monkeypatch):
    pagina = MagicMock()
    navegador = MagicMock()
    navegador.new_page.return_value = pagina
    contexto = MagicMock()
    contexto.__enter__.return_value = navegador
    contexto.__exit__.return_value = False

    constructor = MagicMock(return_value=contexto)
    monkeypatch.setattr("src.ejecutores.camoufox.Camoufox", constructor)
    return constructor, pagina


def test_headless_por_defecto_es_true(monkeypatch):
    constructor, _ = _mockear_camoufox(monkeypatch)
    receta = Receta(nombre="prueba", motor="camoufox", pasos=[])

    CamoufoxEjecutor().ejecutar(receta, {})

    constructor.assert_called_once_with(headless=True, humanize=True)


def test_headless_false_se_pasa_a_camoufox(monkeypatch):
    constructor, _ = _mockear_camoufox(monkeypatch)
    receta = Receta(nombre="prueba", motor="camoufox", headless=False, pasos=[])

    CamoufoxEjecutor().ejecutar(receta, {})

    constructor.assert_called_once_with(headless=False, humanize=True)


def test_extraer_sin_patron_devuelve_el_texto_completo(monkeypatch):
    _, pagina = _mockear_camoufox(monkeypatch)
    pagina.inner_text.return_value = "Example Domains"
    receta = Receta(
        nombre="prueba",
        motor="camoufox",
        pasos=[{"accion": "extraer", "selector": "h1"}],
    )

    resultado = CamoufoxEjecutor().ejecutar(receta, {})

    assert resultado.datos["h1"] == "Example Domains"


def test_extraer_con_patron_busca_dentro_del_texto(monkeypatch):
    _, pagina = _mockear_camoufox(monkeypatch)
    pagina.inner_text.return_value = "Precio: 4500"
    receta = Receta(
        nombre="prueba",
        motor="camoufox",
        pasos=[{"accion": "extraer", "selector": ".precio", "patron": r"\d+"}],
    )

    resultado = CamoufoxEjecutor().ejecutar(receta, {})

    assert resultado.datos[".precio"] == "4500"


def test_clic_usa_force_true(monkeypatch):
    _, pagina = _mockear_camoufox(monkeypatch)
    receta = Receta(
        nombre="prueba",
        motor="camoufox",
        pasos=[{"accion": "clic", "selector": "#boton"}],
    )

    CamoufoxEjecutor().ejecutar(receta, {})

    pagina.click.assert_called_once_with("#boton", force=True)


def test_presionar_llama_press_con_selector_y_tecla(monkeypatch):
    _, pagina = _mockear_camoufox(monkeypatch)
    receta = Receta(
        nombre="prueba",
        motor="camoufox",
        pasos=[{"accion": "presionar", "selector": "#clave", "valor": "Enter"}],
    )

    CamoufoxEjecutor().ejecutar(receta, {})

    pagina.press.assert_called_once_with("#clave", "Enter")
