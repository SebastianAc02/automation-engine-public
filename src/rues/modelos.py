import re

from pydantic import BaseModel, field_validator

_CATEGORIAS = {
    "dueno", "gerente", "rep_legal", "tecnico", "financiero", "operativo",
    "comercial", "rep_legal_suplente", "subgerente", "desconocido",
}

_CELULAR = re.compile(r"^3\d{9}$")


def tipo_numero(numero: str | None) -> str:
    # celular colombiano: 3 + 9 digitos. Lo demas (601..., 7 digitos) es fijo.
    n = re.sub(r"\D", "", numero or "")
    if not n:
        return "desconocido"
    return "celular" if _CELULAR.match(n) else "fijo"


def match_ultimos4(numero: str | None, ultimos4: list[str]) -> bool:
    n = re.sub(r"\D", "", numero or "")
    return bool(n) and any(n.endswith(u) for u in ultimos4 if u)


class EmpresaObjetivo(BaseModel):
    id_empresa: str
    nombre_oficial: str
    nombre_legal: str
    usuarios: float | None = None


class ContactoRues(BaseModel):
    nombre: str
    apellido: str = ""
    cargo: str
    cargo_categoria: str
    documento: str = ""
    es_rep_legal: bool = False
    vigente: bool = True

    @field_validator("cargo_categoria")
    @classmethod
    def _acotar_categoria(cls, valor: str) -> str:
        return valor if valor in _CATEGORIAS else "desconocido"


class TelefonoFuente(BaseModel):
    fuente: str                 # informacolombia | portafolio | einforma | scribd | dian
    numero: str | None = None
    nit_pagina: str | None = None
    tipo: str = "desconocido"   # celular | fijo | desconocido
    nit_verificado: bool = False        # el NIT de la pagina coincide (directorios)
    match_dian: bool = False            # termina en un ultimo-4 de la DIAN
    # supremamente confirmado = celular que hace match con la DIAN (el cel del rep).
    # Un fijo verificado por NIT NO es supremamente confirmado.
    supremamente_confirmado: bool = False
    estado: str = "ok"          # ok | no_encontrado


class ResultadoEmpresa(BaseModel):
    id_empresa: str
    contactos: list[ContactoRues] = []
    telefonos: list[TelefonoFuente] = []
    rues_error: str | None = None
    # estado_matricula tal cual lo trae RUES (ej: "ACTIVA", "CANCELADA"). Si la
    # empresa esta cancelada, el rep legal que sale puede ser historico y no
    # vigente: se guarda para poder marcarlo, nunca se descarta en silencio.
    estado_matricula: str | None = None
