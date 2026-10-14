import time

import httpx

from config.settings import settings
from src.ejecutores.base import EjecutorBase, coincidencia_texto
from src.models import Receta, Resultado


class TrawlEjecutor(EjecutorBase):
    def ejecutar(self, receta: Receta, datos: dict) -> Resultado:
        if not settings.trawl_url:
            return Resultado(exito=False, error="TRAWL_URL no configurado")

        extraido = {}
        cuerpo_actual = ""
        timeout_ms = int(settings.timeout_default * 1000)

        with httpx.Client(timeout=settings.timeout_default + 30) as cliente:
            for paso in receta.pasos:
                paso = paso.resuelto(datos)

                if paso.accion == "navegar":
                    respuesta = cliente.post(
                        f"{settings.trawl_url}/scrape",
                        json={"url": paso.url, "maxTimeout": timeout_ms},
                    )
                    respuesta.raise_for_status()
                    resuelto = respuesta.json()
                    if resuelto["statusCode"] >= 400:
                        raise RuntimeError(f"trawl: {paso.url} devolvio {resuelto['statusCode']}")
                    cuerpo_actual = resuelto["html"]

                elif paso.accion == "extraer":
                    extraido[paso.selector] = (
                        coincidencia_texto(paso.patron, cuerpo_actual) if paso.patron else cuerpo_actual
                    )

                elif paso.accion == "esperar":
                    time.sleep(paso.segundos)

        return Resultado(exito=True, datos=extraido)
