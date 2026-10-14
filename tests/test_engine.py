from unittest.mock import MagicMock

from src.ejecutores import EJECUTORES
from src.ejecutores.base import EjecutorBase
from src.engine import ejecutar_receta
from src.models import Receta, Resultado


def test_registro_tiene_los_tres_motores():
    assert set(EJECUTORES) == {"camoufox", "trawl", "httpx"}
    assert all(isinstance(ejecutor, EjecutorBase) for ejecutor in EJECUTORES.values())


def test_ejecutar_receta_resuelve_motor_por_registro(monkeypatch):
    esperado = Resultado(exito=True, datos={"x": 1})
    ejecutor_falso = MagicMock()
    ejecutor_falso.ejecutar.return_value = esperado
    monkeypatch.setitem(EJECUTORES, "httpx", ejecutor_falso)

    receta = Receta(nombre="prueba", motor="httpx", pasos=[])
    resultado, intentos, _ = ejecutar_receta(receta, {"k": "v"})

    assert resultado == esperado
    assert intentos == 1
    ejecutor_falso.ejecutar.assert_called_once_with(receta, {"k": "v"})


def test_ejecutar_receta_reintenta_con_backoff_y_falla_tras_tres_intentos(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda segundos: None)
    ejecutor_falso = MagicMock()
    ejecutor_falso.ejecutar.side_effect = RuntimeError("motor caido")
    monkeypatch.setitem(EJECUTORES, "httpx", ejecutor_falso)

    receta = Receta(nombre="prueba", motor="httpx", pasos=[])
    resultado, intentos, _ = ejecutar_receta(receta, {})

    assert resultado.exito is False
    assert "motor caido" in resultado.error
    assert intentos == 3
    assert ejecutor_falso.ejecutar.call_count == 3


def test_ejecutar_receta_no_reintenta_si_el_primer_intento_funciona(monkeypatch):
    ejecutor_falso = MagicMock()
    ejecutor_falso.ejecutar.return_value = Resultado(exito=True)
    monkeypatch.setitem(EJECUTORES, "httpx", ejecutor_falso)

    receta = Receta(nombre="prueba", motor="httpx", pasos=[])
    _, intentos, _ = ejecutar_receta(receta, {})

    assert intentos == 1
