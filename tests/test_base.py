from src.ejecutores.base import coincidencia_texto


def test_coincidencia_texto_sin_grupo_devuelve_el_match_completo():
    assert coincidencia_texto(r"\d+", "precio: 4500 pesos") == "4500"


def test_coincidencia_texto_con_grupo_devuelve_solo_el_grupo():
    assert coincidencia_texto(r'"telephone":"(\d+)"', '{"telephone":"3205582644"}') == "3205582644"


def test_coincidencia_texto_sin_match_devuelve_none():
    assert coincidencia_texto(r"\d+", "sin numeros aqui") is None
