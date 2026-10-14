import re
import unicodedata

_DIRECTORIOS_MAYUS = {"portafolio"}


def normalizar(texto: str) -> str:
    sin_tilde = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    solo_validos = re.sub(r"[^0-9A-Za-z\s]", " ", sin_tilde)
    return re.sub(r"\s+", " ", solo_validos).strip()


def _a_slug(palabras: list[str], directorio: str) -> str:
    unido = "-".join(palabras)
    return unido.upper() if directorio in _DIRECTORIOS_MAYUS else unido.lower()


def generar_slugs(razon_social: str, directorio: str) -> list[str]:
    palabras = normalizar(razon_social).split()
    variantes = [palabras]
    if any(p.lower() == "telecomunicaciones" for p in palabras):
        variantes.append(
            ["comunicaciones" if p.lower() == "telecomunicaciones" else p for p in palabras]
        )
    slugs: list[str] = []
    for variante in variantes:
        candidato = _a_slug(variante, directorio)
        if candidato not in slugs:
            slugs.append(candidato)
    return slugs
