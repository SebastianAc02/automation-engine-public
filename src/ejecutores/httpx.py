import time

import httpx

from src.ejecutores.base import EjecutorBase, coincidencia_texto
from src.models import Receta, Resultado


class HttpxEjecutor(EjecutorBase):
    def ejecutar(self, receta: Receta, datos: dict) -> Resultado:
        extraido = {}
        cuerpo_actual = ""

        with httpx.Client(timeout=30.0) as cliente:
            for paso in receta.pasos:
                paso = paso.resuelto(datos)

                if paso.accion == "navegar":
                    if paso.valor is not None:
                        respuesta = cliente.post(paso.url, data={"valor": paso.valor})
                    else:
                        respuesta = cliente.get(paso.url)
                    respuesta.raise_for_status()
                    cuerpo_actual = respuesta.text

                elif paso.accion == "extraer":
                    extraido[paso.selector] = (
                        coincidencia_texto(paso.patron, cuerpo_actual) if paso.patron else cuerpo_actual
                    )

                elif paso.accion == "esperar":
                    time.sleep(paso.segundos)

        return Resultado(exito=True, datos=extraido)
