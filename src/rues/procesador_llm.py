import json

import anthropic
from pydantic import BaseModel

from src.rues.modelos import ContactoRues


class _Representantes(BaseModel):
    contactos: list[ContactoRues]


_SISTEMA = (
    "Extraes los representantes de una empresa colombiana del JSON crudo del RUES. "
    "Devuelve solo los vigentes; ignora los historicos. Para cada persona: nombre, "
    "apellido, cargo textual como aparece, cargo_categoria en {rep_legal, "
    "rep_legal_suplente, gerente, subgerente, dueno, tecnico, financiero, operativo, "
    "comercial, desconocido}, documento (cedula, solo digitos), es_rep_legal true solo "
    "para el representante legal principal."
)


def procesar_representantes(raw: dict, api_key: str, modelo: str = "claude-sonnet-5") -> list[ContactoRues]:
    cliente = anthropic.Anthropic(api_key=api_key)
    respuesta = cliente.messages.parse(
        model=modelo,
        max_tokens=4000,
        system=_SISTEMA,
        messages=[{"role": "user", "content": json.dumps(raw, ensure_ascii=False)}],
        output_format=_Representantes,
    )
    return respuesta.parsed_output.contactos
