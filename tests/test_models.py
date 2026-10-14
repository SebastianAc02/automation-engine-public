from src.models import Receta, variables_de


def test_variables_de_detecta_nombres_unicos_en_orden_de_aparicion():
    receta = Receta(
        nombre="prueba",
        motor="httpx",
        pasos=[
            {"accion": "navegar", "url": "https://example.com/{{data.slug}}"},
            {"accion": "rellenar", "selector": "#doc", "valor": "{{data.cedula}}"},
            {"accion": "clic", "selector": "button:has-text('{{data.cedula}}')"},
        ],
    )

    assert variables_de(receta) == ["slug", "cedula"]


def test_variables_de_vacio_si_no_hay_variables():
    receta = Receta(
        nombre="prueba",
        motor="httpx",
        pasos=[{"accion": "navegar", "url": "https://example.com"}],
    )

    assert variables_de(receta) == []
