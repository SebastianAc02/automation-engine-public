import re
from typing import Literal

from pydantic import BaseModel

TipoPaso = Literal[
    "navegar", "clic", "rellenar", "extraer", "esperar", "ejecutar_js", "presionar",
    "esperar_texto", "estructurar_llm", "resolver_captcha", "repetir_hasta", "condicional",
]

_PATRON_VARIABLE = re.compile(r"\{\{data\.(\w+)\}\}")


class ParadaCoincidencia(BaseModel):
    """Condicion de parada para repetir_hasta: compara un valor ya extraido
    (campo, una clave de `extraido`) contra un valor esperado (igual_a,
    admite {{data.x}}). tolerancia_digito_extra reproduce la tolerancia de
    NIT (el extraido trae un digito de verificacion de mas al final)."""
    campo: str
    igual_a: str
    tolerancia_digito_extra: bool = False


class Paso(BaseModel):
    accion: TipoPaso
    url: str | None = None
    selector: str | None = None
    valor: str | None = None
    patron: str | None = None
    segundos: float | None = None
    script: str | None = None
    salida: str | None = None
    # repetir_hasta / condicional
    pasos: list["Paso"] | None = None
    max_intentos: int | None = None
    parar_si: ParadaCoincidencia | None = None
    si_vacio: str | None = None

    def resuelto(self, datos: dict) -> "Paso":
        campos = self.model_dump()
        for campo in ("url", "selector", "valor", "patron", "script", "salida", "si_vacio"):
            if campos[campo] is not None:
                campos[campo] = _PATRON_VARIABLE.sub(
                    lambda m: str(datos.get(m.group(1), m.group(0))), campos[campo]
                )
        if campos.get("parar_si") and campos["parar_si"].get("igual_a"):
            campos["parar_si"]["igual_a"] = _PATRON_VARIABLE.sub(
                lambda m: str(datos.get(m.group(1), m.group(0))), campos["parar_si"]["igual_a"]
            )
        # las sub-listas de pasos (repetir_hasta/condicional) se resuelven
        # aparte en el ejecutor, paso por paso, igual que los del nivel raiz:
        # aca solo se devuelven tal cual (Paso ya los parseo desde el dict).
        return Paso(**campos)


Paso.model_rebuild()


class Receta(BaseModel):
    nombre: str
    motor: str
    descripcion: str = ""
    headless: bool = True
    perfil: str | None = None
    pasos: list[Paso]


class Resultado(BaseModel):
    exito: bool
    datos: dict = {}
    error: str | None = None


def variables_de(receta: Receta) -> list[str]:
    encontradas = []
    for paso in receta.pasos:
        for campo in ("url", "selector", "valor", "patron", "script"):
            valor = getattr(paso, campo)
            if valor is None:
                continue
            for nombre in _PATRON_VARIABLE.findall(valor):
                if nombre not in encontradas:
                    encontradas.append(nombre)
    return encontradas
