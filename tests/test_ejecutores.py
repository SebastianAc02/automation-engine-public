from unittest.mock import MagicMock

import pytest

from src.ejecutores.base import EjecutorBase
from src.ejecutores.httpx import HttpxEjecutor
from src.models import Paso, Receta


def test_ejecutor_base_es_abstracta():
    with pytest.raises(TypeError):
        EjecutorBase()


def test_paso_resuelve_variables():
    paso = Paso(accion="navegar", url="https://example.com/{{data.ruta}}")
    resuelto = paso.resuelto({"ruta": "inicio"})
    assert resuelto.url == "https://example.com/inicio"


def test_paso_deja_variable_sin_resolver_si_falta_el_dato():
    paso = Paso(accion="navegar", url="https://example.com/{{data.ruta}}")
    resuelto = paso.resuelto({})
    assert resuelto.url == "https://example.com/{{data.ruta}}"


def test_httpx_ejecutor_navega_y_extrae_el_match_completo_sin_grupo(monkeypatch):
    respuesta = MagicMock()
    respuesta.text = "<title>Hola</title>"

    cliente = MagicMock()
    cliente.get.return_value = respuesta
    cliente.__enter__.return_value = cliente
    cliente.__exit__.return_value = False
    monkeypatch.setattr("src.ejecutores.httpx.httpx.Client", lambda **kwargs: cliente)

    receta = Receta(
        nombre="prueba",
        motor="httpx",
        pasos=[
            {"accion": "navegar", "url": "https://example.com"},
            {"accion": "extraer", "selector": "titulo", "patron": "<title>.*?</title>"},
        ],
    )

    resultado = HttpxEjecutor().ejecutar(receta, {})

    assert resultado.exito
    assert resultado.datos["titulo"] == "<title>Hola</title>"
    cliente.get.assert_called_once_with("https://example.com")


def test_httpx_ejecutor_con_grupo_de_captura_devuelve_solo_el_grupo(monkeypatch):
    respuesta = MagicMock()
    respuesta.text = "<title>Hola</title>"

    cliente = MagicMock()
    cliente.get.return_value = respuesta
    cliente.__enter__.return_value = cliente
    cliente.__exit__.return_value = False
    monkeypatch.setattr("src.ejecutores.httpx.httpx.Client", lambda **kwargs: cliente)

    receta = Receta(
        nombre="prueba",
        motor="httpx",
        pasos=[
            {"accion": "navegar", "url": "https://example.com"},
            {"accion": "extraer", "selector": "titulo", "patron": "<title>(.*?)</title>"},
        ],
    )

    resultado = HttpxEjecutor().ejecutar(receta, {})

    assert resultado.datos["titulo"] == "Hola"


def test_httpx_ejecutor_sin_patron_devuelve_el_texto_completo(monkeypatch):
    respuesta = MagicMock()
    respuesta.text = "<title>Hola</title>"

    cliente = MagicMock()
    cliente.get.return_value = respuesta
    cliente.__enter__.return_value = cliente
    cliente.__exit__.return_value = False
    monkeypatch.setattr("src.ejecutores.httpx.httpx.Client", lambda **kwargs: cliente)

    receta = Receta(
        nombre="prueba",
        motor="httpx",
        pasos=[
            {"accion": "navegar", "url": "https://example.com"},
            {"accion": "extraer", "selector": "titulo"},
        ],
    )

    resultado = HttpxEjecutor().ejecutar(receta, {})

    assert resultado.datos["titulo"] == "<title>Hola</title>"


def test_httpx_ejecutor_extrae_none_si_no_hay_coincidencia(monkeypatch):
    respuesta = MagicMock()
    respuesta.text = "sin titulo aqui"

    cliente = MagicMock()
    cliente.get.return_value = respuesta
    cliente.__enter__.return_value = cliente
    cliente.__exit__.return_value = False
    monkeypatch.setattr("src.ejecutores.httpx.httpx.Client", lambda **kwargs: cliente)

    receta = Receta(
        nombre="prueba",
        motor="httpx",
        pasos=[
            {"accion": "navegar", "url": "https://example.com"},
            {"accion": "extraer", "selector": "titulo", "patron": "<title>(.*?)</title>"},
        ],
    )

    resultado = HttpxEjecutor().ejecutar(receta, {})

    assert resultado.datos["titulo"] is None
