import re
from pathlib import Path

import typer
import yaml

from config.settings import settings
from src.engine import ejecutar_receta
from src.grabador.parser import selector_desde_codigo
from src.models import Paso, Receta, variables_de

_PLANTILLA_ESPERAR = """(() => {{
  return new Promise((resolve) => {{
    const revisar = () => {{
      if (document.querySelector('{selector}')) resolve(true);
      else setTimeout(revisar, 200);
    }};
    revisar();
  }});
}})();"""

_PLANTILLA_OVERLAY = """(() => {{
  const el = document.querySelector('{selector}');
  if (el) el.click();
}})();"""


def armar_receta(elementos: list[dict], nombre: str, motor: str) -> Path:
    pasos = [
        _resolver_no_reconocido(elemento) if elemento.get("no_reconocido") else elemento
        for elemento in elementos
    ]

    _preguntar_variables(pasos)
    pasos.extend(_preguntar_extraccion())
    pasos = _verificar_selectores(pasos, motor)

    receta = Receta(
        nombre=nombre,
        motor=motor,
        descripcion="Receta generada automaticamente",
        pasos=[Paso(**paso) for paso in pasos],
    )

    yaml_texto = yaml.dump(receta.model_dump(exclude_none=True), allow_unicode=True, sort_keys=False)
    typer.echo(yaml_texto)

    settings.dir_recetas.mkdir(exist_ok=True)
    ruta = settings.dir_recetas / f"{nombre}.yaml"
    ruta.write_text(yaml_texto)
    return ruta


def _resolver_no_reconocido(entrada: dict) -> dict:
    typer.echo(f"No pude traducir esto solo. Lo que grabé fue: {entrada['codigo']}")
    typer.echo("¿Qué debe pasar aquí?")
    typer.echo("  1. Un clic normal (te pido el selector)")
    typer.echo("  2. Rellenar un campo (te pido selector y valor)")
    typer.echo("  3. Extraer un dato (te pido selector y patrón)")
    typer.echo("  4. Otra cosa (elige una plantilla ya probada)")
    opcion = typer.prompt("Elige una opción")

    if opcion == "1":
        return {"accion": "clic", "selector": _pedir_selector()}
    if opcion == "2":
        return {
            "accion": "rellenar",
            "selector": _pedir_selector(),
            "valor": typer.prompt("Valor"),
        }
    if opcion == "3":
        return {"accion": "extraer", "selector": _pedir_selector(), "patron": _pedir_patron()}

    return _resolver_plantilla()


def _resolver_plantilla() -> dict:
    typer.echo("  1. Esperar a que aparezca un elemento")
    typer.echo("  2. Cerrar un overlay o modal")
    plantilla = typer.prompt("Elige una plantilla")
    selector = typer.prompt("Selector")

    if plantilla == "1":
        script = _PLANTILLA_ESPERAR.format(selector=selector)
    else:
        script = _PLANTILLA_OVERLAY.format(selector=selector)

    return {"accion": "ejecutar_js", "script": script}


def _preguntar_variables(pasos: list[dict]) -> None:
    usados = {}
    for paso in pasos:
        if paso["accion"] != "rellenar" or not paso.get("valor"):
            continue
        nombre = _nombre_variable(paso["selector"])
        usados[nombre] = usados.get(nombre, 0) + 1
        if usados[nombre] > 1:
            nombre = f"{nombre}_{usados[nombre]}"
        paso["valor"] = f"{{{{data.{nombre}}}}}"


def _nombre_variable(selector: str) -> str:
    coincidencia = re.search(r'name="([^"]+)"|placeholder="([^"]+)"', selector)
    texto = next((g for g in coincidencia.groups() if g), None) if coincidencia else None
    if texto is None:
        texto = selector.lstrip("#.")
    limpio = re.sub(r"[^a-zA-Z0-9]+", "_", texto).strip("_").lower()
    return limpio or "campo"


def _preguntar_extraccion() -> list[dict]:
    pasos = []
    while typer.confirm("¿Quieres agregar otro paso de extraccion?", default=False):
        pasos.append({"accion": "extraer", "selector": _pedir_selector(), "patron": _pedir_patron()})
    return pasos


def _pedir_selector() -> str:
    codigo = typer.prompt("Pega lo que copiaste del navegador (o el selector directo)")
    return selector_desde_codigo(codigo) or codigo


def _pedir_patron() -> str | None:
    respuesta = typer.prompt(
        "Enter para traer todo el texto tal cual (recomendado). Si necesitas solo una "
        "parte especifica, escribe el patron regex que la busca",
        default="",
        show_default=False,
    )
    return respuesta or None


def _verificar_selectores(pasos: list[dict], motor: str) -> list[dict]:
    if motor != "camoufox" or not pasos:
        return pasos

    typer.echo("Verificando que los selectores existan de verdad, un momento...")
    while True:
        borrador = Receta(nombre="_verificacion", motor=motor, pasos=[Paso(**p) for p in pasos])
        datos_prueba = {campo: "prueba" for campo in variables_de(borrador)}
        resultado, _, _ = ejecutar_receta(borrador, datos_prueba)

        if resultado.exito:
            typer.echo("Todos los selectores existen.")
            return pasos

        typer.echo(f"Un paso fallo: {resultado.error}")
        indice = _ubicar_paso_fallido(pasos, resultado.error or "")

        if indice is None:
            if typer.confirm("No pude identificar cual selector fallo. ¿Guardar de todas formas?", default=False):
                return pasos
            raise typer.Exit(1)

        typer.echo(f"Parece ser este paso: {pasos[indice]}")
        pasos[indice]["selector"] = _pedir_selector()


def _ubicar_paso_fallido(pasos: list[dict], error: str) -> int | None:
    for indice, paso in enumerate(pasos):
        selector = paso.get("selector")
        if selector and selector in error:
            return indice
    return None
