import re


def normalizar_nit(bruto: str) -> str:
    return re.sub(r"\D", "", bruto or "")


def nit_encaja(nit_pagina: str, nit_empresa: str) -> bool:
    a = normalizar_nit(nit_pagina)
    b = normalizar_nit(nit_empresa)
    if not a or not b:
        return False
    if a == b:
        return True
    # tolerancia al digito de verificacion: uno es el otro sin su ultimo digito
    return a == b[:-1] or b == a[:-1]
