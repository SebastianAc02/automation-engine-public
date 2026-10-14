from unittest.mock import MagicMock

import pytest

from src.ejecutores.trawl import TrawlEjecutor
from src.models import Receta


def _mockear_cliente(monkeypatch, html, status_code=200):
    respuesta = MagicMock()
    respuesta.json.return_value = {"html": html, "statusCode": status_code}

    cliente = MagicMock()
    cliente.post.return_value = respuesta
    cliente.__enter__.return_value = cliente
    cliente.__exit__.return_value = False
    monkeypatch.setattr("src.ejecutores.trawl.httpx.Client", lambda **kwargs: cliente)
    return cliente


def test_sin_trawl_url_devuelve_error_claro(monkeypatch):
    monkeypatch.setattr("src.ejecutores.trawl.settings.trawl_url", "")
    receta = Receta(nombre="prueba", motor="trawl", pasos=[])

    resultado = TrawlEjecutor().ejecutar(receta, {})

    assert resultado.exito is False
    assert "TRAWL_URL" in resultado.error


def test_navegar_llama_scrape_con_la_url_y_extrae_del_html(monkeypatch):
    monkeypatch.setattr("src.ejecutores.trawl.settings.trawl_url", "http://localhost:8291")
    cliente = _mockear_cliente(monkeypatch, html='<span itemprop="telephone">3205582644</span>')

    receta = Receta(
        nombre="prueba",
        motor="trawl",
        pasos=[
            {"accion": "navegar", "url": "https://example.com"},
            {"accion": "extraer", "selector": "telefono", "patron": r"\d+"},
        ],
    )

    resultado = TrawlEjecutor().ejecutar(receta, {})

    assert resultado.exito
    assert resultado.datos["telefono"] == "3205582644"
    cliente.post.assert_called_once_with(
        "http://localhost:8291/scrape",
        json={"url": "https://example.com", "maxTimeout": 30000},
    )


def test_status_code_de_error_lanza_excepcion(monkeypatch):
    monkeypatch.setattr("src.ejecutores.trawl.settings.trawl_url", "http://localhost:8291")
    _mockear_cliente(monkeypatch, html="", status_code=403)

    receta = Receta(
        nombre="prueba",
        motor="trawl",
        pasos=[{"accion": "navegar", "url": "https://example.com"}],
    )

    with pytest.raises(RuntimeError, match="403"):
        TrawlEjecutor().ejecutar(receta, {})
