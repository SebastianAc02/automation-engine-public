import yaml

from src.grabador.receta import armar_receta
from src.models import Receta, Resultado


def test_armar_receta_genera_yaml_valido_con_variables(monkeypatch, tmp_path):
    monkeypatch.setattr("src.grabador.receta.settings.dir_recetas", tmp_path)
    monkeypatch.setattr("src.grabador.receta.typer.confirm", lambda *args, **kwargs: False)

    elementos = [
        {"accion": "navegar", "url": "https://example.com/login"},
        {"accion": "rellenar", "selector": "#usuario", "valor": "admin@example.com"},
        {"accion": "clic", "selector": "#entrar"},
    ]

    ruta = armar_receta(elementos, "receta-prueba", "httpx")

    assert ruta == tmp_path / "receta-prueba.yaml"
    contenido = yaml.safe_load(ruta.read_text())

    assert contenido["nombre"] == "receta-prueba"
    assert contenido["motor"] == "httpx"
    assert contenido["descripcion"] == "Receta generada automaticamente"
    assert contenido["pasos"][1]["valor"] == "{{data.usuario}}"

    receta = Receta(**contenido)
    assert len(receta.pasos) == 3


def test_armar_receta_infiere_nombre_de_variable_del_selector(monkeypatch, tmp_path):
    monkeypatch.setattr("src.grabador.receta.settings.dir_recetas", tmp_path)
    monkeypatch.setattr("src.grabador.receta.typer.confirm", lambda *args, **kwargs: False)

    elementos = [
        {"accion": "rellenar", "selector": 'role=textbox[name="Password"]', "valor": "secreto123"}
    ]

    ruta = armar_receta(elementos, "receta-password", "httpx")
    contenido = yaml.safe_load(ruta.read_text())

    assert contenido["pasos"][0]["valor"] == "{{data.password}}"
    Receta(**contenido)


def test_armar_receta_desambigua_nombres_de_variable_repetidos(monkeypatch, tmp_path):
    monkeypatch.setattr("src.grabador.receta.settings.dir_recetas", tmp_path)
    monkeypatch.setattr("src.grabador.receta.typer.confirm", lambda *args, **kwargs: False)

    elementos = [
        {"accion": "rellenar", "selector": 'role=textbox[name="Clave"]', "valor": "uno"},
        {"accion": "rellenar", "selector": 'role=textbox[name="Clave"]', "valor": "dos"},
    ]

    ruta = armar_receta(elementos, "receta-repetida", "httpx")
    contenido = yaml.safe_load(ruta.read_text())

    assert contenido["pasos"][0]["valor"] == "{{data.clave}}"
    assert contenido["pasos"][1]["valor"] == "{{data.clave_2}}"
    Receta(**contenido)


def test_armar_receta_resuelve_no_reconocido_en_su_posicion_original(monkeypatch, tmp_path):
    monkeypatch.setattr("src.grabador.receta.settings.dir_recetas", tmp_path)
    monkeypatch.setattr(
        "src.grabador.receta.ejecutar_receta", lambda *a, **k: (Resultado(exito=True), 1, 10)
    )

    respuestas = iter(["4", "2", ".modal-cerrar"])
    monkeypatch.setattr("src.grabador.receta.typer.prompt", lambda *args, **kwargs: next(respuestas))
    monkeypatch.setattr("src.grabador.receta.typer.confirm", lambda *args, **kwargs: False)

    elementos = [
        {"accion": "navegar", "url": "https://example.com/panel"},
        {"no_reconocido": True, "codigo": 'page.get_by_role("link", name="X").hover()', "linea": 7},
        {"accion": "clic", "selector": "#continuar"},
    ]

    ruta = armar_receta(elementos, "receta-overlay", "camoufox")
    contenido = yaml.safe_load(ruta.read_text())

    pasos = contenido["pasos"]
    assert pasos[0]["accion"] == "navegar"
    assert pasos[1]["accion"] == "ejecutar_js"
    assert ".modal-cerrar" in pasos[1]["script"]
    assert pasos[2]["accion"] == "clic"

    receta = Receta(**contenido)
    assert receta.pasos[1].accion == "ejecutar_js"


def test_armar_receta_agrega_pasos_de_extraccion_al_final(monkeypatch, tmp_path):
    monkeypatch.setattr("src.grabador.receta.settings.dir_recetas", tmp_path)

    confirmaciones = iter([True, False])
    monkeypatch.setattr("src.grabador.receta.typer.confirm", lambda *args, **kwargs: next(confirmaciones))

    respuestas = iter([".precio", r"\d+"])
    monkeypatch.setattr("src.grabador.receta.typer.prompt", lambda *args, **kwargs: next(respuestas))

    elementos = [{"accion": "navegar", "url": "https://example.com"}]

    ruta = armar_receta(elementos, "receta-con-extraccion", "httpx")
    contenido = yaml.safe_load(ruta.read_text())

    pasos = contenido["pasos"]
    assert len(pasos) == 2
    assert pasos[1] == {"accion": "extraer", "selector": ".precio", "patron": r"\d+"}

    receta = Receta(**contenido)
    assert receta.pasos[1].accion == "extraer"


def test_verificacion_detecta_selector_roto_y_deja_corregirlo(monkeypatch, tmp_path):
    monkeypatch.setattr("src.grabador.receta.settings.dir_recetas", tmp_path)
    monkeypatch.setattr("src.grabador.receta.typer.confirm", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "src.grabador.receta.typer.prompt", lambda *args, **kwargs: "role=heading[name=\"Example Domain\"]"
    )

    intentos = iter(
        [
            (Resultado(exito=False, error='esperando role=heading[name="Example Domains"]'), 3, 100),
            (Resultado(exito=True), 1, 50),
        ]
    )
    monkeypatch.setattr("src.grabador.receta.ejecutar_receta", lambda *a, **k: next(intentos))

    elementos = [
        {"accion": "navegar", "url": "https://example.com"},
        {"accion": "extraer", "selector": 'role=heading[name="Example Domains"]'},
    ]

    ruta = armar_receta(elementos, "receta-verificada", "camoufox")
    contenido = yaml.safe_load(ruta.read_text())

    assert contenido["pasos"][1]["selector"] == 'role=heading[name="Example Domain"]'


def test_verificacion_no_aplica_a_motores_sin_navegador(monkeypatch, tmp_path):
    monkeypatch.setattr("src.grabador.receta.settings.dir_recetas", tmp_path)
    monkeypatch.setattr("src.grabador.receta.typer.confirm", lambda *args, **kwargs: False)

    def falla_si_se_llama(*a, **k):
        raise AssertionError("no deberia verificar recetas httpx/trawl")

    monkeypatch.setattr("src.grabador.receta.ejecutar_receta", falla_si_se_llama)

    elementos = [{"accion": "navegar", "url": "https://example.com"}]
    armar_receta(elementos, "receta-sin-verificar", "httpx")
