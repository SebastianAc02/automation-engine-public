import csv
import json
import sys
from datetime import datetime

import typer
import yaml
from loguru import logger
from pydantic import ValidationError

from config.settings import settings
from src.engine import cargar_receta, ejecutar_receta
from src.flujos.directorio import (
    buscar_empresa_einforma,
    buscar_empresa_informacolombia,
    buscar_empresa_portafolio,
)
from src.flujos.scribd import buscar_telefono_scribd, buscar_y_extraer_scribd
from src.grabador.grabar import grabar as grabar_sesion
from src.grabador.parser import parsear
from src.grabador.receta import armar_receta
from src.models import variables_de

app = typer.Typer()

logger.remove()
logger.add(sys.stderr, level=settings.log_level)


@app.command()
def ejecutar(
    receta: str,
    data: str = typer.Option(None, "--data"),
    data_file: str = typer.Option(None, "--data-file"),
    data_csv: str = typer.Option(None, "--data-csv"),
    data_interactivo: bool = typer.Option(False, "--data-interactivo"),
    headless: bool = typer.Option(None, "--headless/--no-headless"),
):
    ruta = settings.dir_recetas / f"{receta}.yaml"
    receta_cargada = cargar_receta(str(ruta))
    if headless is not None:
        receta_cargada.headless = headless

    if data_csv:
        exitosas = 0
        with open(data_csv, newline="") as f:
            filas = list(csv.DictReader(f))
        for i, fila in enumerate(filas, start=1):
            resultado, intentos, duracion_ms = ejecutar_receta(receta_cargada, dict(fila))
            _guardar_resultado(receta, receta_cargada.motor, resultado, intentos, duracion_ms, sufijo=str(i))
            exitosas += resultado.exito
        typer.echo(f"{exitosas}/{len(filas)} filas exitosas")
        raise typer.Exit(0 if exitosas == len(filas) else 1)

    if data_interactivo:
        datos = {campo: typer.prompt(f"Valor para '{campo}'") for campo in variables_de(receta_cargada)}
    else:
        datos = {}
        if data:
            datos.update(json.loads(data))
        if data_file:
            datos.update(json.loads(open(data_file).read()))

    resultado, intentos, duracion_ms = ejecutar_receta(receta_cargada, datos)
    _guardar_resultado(receta, receta_cargada.motor, resultado, intentos, duracion_ms)

    typer.echo(resultado.model_dump_json(indent=2))
    raise typer.Exit(0 if resultado.exito else 1)


def _guardar_resultado(receta, motor, resultado, intentos, duracion_ms, sufijo=""):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    nombre_archivo = f"{receta}_{sufijo}_{timestamp}" if sufijo else f"{receta}_{timestamp}"
    settings.dir_resultados.mkdir(exist_ok=True)
    (settings.dir_resultados / f"{nombre_archivo}.json").write_text(resultado.model_dump_json(indent=2))

    settings.dir_logs.mkdir(exist_ok=True)
    linea_log = {
        "receta": receta,
        "motor": motor,
        "exito": resultado.exito,
        "duracion_ms": duracion_ms,
        "intentos": intentos,
    }
    with open(settings.dir_logs / "engine.jsonl", "a") as f:
        f.write(json.dumps(linea_log) + "\n")


@app.command()
def listar():
    for ruta in sorted(settings.dir_recetas.glob("*.yaml")):
        receta = cargar_receta(str(ruta))
        typer.echo(f"{receta.nombre}\tmotor={receta.motor}\t{receta.descripcion}")


@app.command()
def validar(receta: str):
    ruta = settings.dir_recetas / f"{receta}.yaml"
    try:
        cargar_receta(str(ruta))
    except ValidationError as error:
        typer.echo(f"receta invalida: {error}")
        raise typer.Exit(1)
    except (yaml.YAMLError, FileNotFoundError) as error:
        typer.echo(f"error leyendo '{ruta}': {error}")
        raise typer.Exit(1)
    typer.echo(f"'{receta}' es valida")


@app.command()
def grabar(
    url: str,
    nombre: str = typer.Option(..., "--nombre"),
    motor: str = typer.Option("camoufox", "--motor"),
):
    typer.echo(
        "Se abre el navegador. Interactua normal: clic simple en lo que quieras que la "
        "receta repita, rellena los campos con un valor de ejemplo real. Para marcar un "
        "dato que quieres extraer, hazle DOBLE clic en vez de uno normal, eso ya lo marca "
        "solo, no hace falta nada mas."
    )
    codigo = grabar_sesion(url)
    elementos = parsear(codigo)
    ruta = armar_receta(elementos, nombre, motor)
    typer.echo(f"Receta guardada en '{ruta}'")


@app.command()
def buscar_scribd(
    query: str,
    headless: bool = typer.Option(True, "--headless/--no-headless"),
):
    documentos = buscar_y_extraer_scribd(query, headless=headless)
    typer.echo(json.dumps(documentos, indent=2, ensure_ascii=False))


@app.command()
def empresa_einforma(
    query: str,
    nit: str,
    headless: bool = typer.Option(True, "--headless/--no-headless"),
):
    resultado = buscar_empresa_einforma(query, nit, headless=headless)
    typer.echo(json.dumps(resultado, indent=2, ensure_ascii=False))


@app.command()
def empresa_informacolombia(
    query: str,
    nit: str,
    headless: bool = typer.Option(True, "--headless/--no-headless"),
):
    resultado = buscar_empresa_informacolombia(query, nit, headless=headless)
    typer.echo(json.dumps(resultado, indent=2, ensure_ascii=False))


@app.command()
def empresa_portafolio(
    query: str,
    nit: str,
    headless: bool = typer.Option(True, "--headless/--no-headless"),
):
    resultado = buscar_empresa_portafolio(query, nit, headless=headless)
    typer.echo(json.dumps(resultado, indent=2, ensure_ascii=False))


@app.command()
def telefono_scribd(
    nombre: str,
    ultimos4: list[str] = typer.Argument(..., help="uno o mas grupos de 4 digitos a buscar"),
    headless: bool = typer.Option(True, "--headless/--no-headless"),
):
    resultado = buscar_telefono_scribd(nombre, ultimos4, headless=headless)
    typer.echo(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
