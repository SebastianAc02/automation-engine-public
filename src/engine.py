import time

import yaml
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.ejecutores import EJECUTORES
from src.models import Receta, Resultado


def cargar_receta(ruta: str) -> Receta:
    # encoding explicito: sin esto, en Windows el default es cp1252 (no utf-8
    # como en Mac/Linux) y las tildes de los selectores (ej. "¿Olvidó su
    # contraseña?") se leen mal, rompiendo cualquier match contra la pagina real.
    with open(ruta, encoding="utf-8") as f:
        return Receta(**yaml.safe_load(f))


def ejecutar_receta(receta: Receta, datos: dict) -> tuple[Resultado, int, int]:
    ejecutor = EJECUTORES[receta.motor]
    intentos = 0
    inicio = time.monotonic()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4), reraise=True)
    def intentar() -> Resultado:
        nonlocal intentos
        intentos += 1
        logger.info(f"intento {intentos}: receta='{receta.nombre}' motor='{receta.motor}'")
        return ejecutor.ejecutar(receta, datos)

    try:
        resultado = intentar()
    except Exception as error:
        resultado = Resultado(exito=False, error=str(error))

    duracion_ms = int((time.monotonic() - inicio) * 1000)
    return resultado, intentos, duracion_ms
