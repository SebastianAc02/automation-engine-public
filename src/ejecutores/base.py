import re
from abc import ABC, abstractmethod

from src.models import Receta, Resultado


class EjecutorBase(ABC):
    @abstractmethod
    def ejecutar(self, receta: Receta, datos: dict) -> Resultado: ...


def coincidencia_texto(patron: str, texto: str) -> str | None:
    coincidencia = re.search(patron, texto)
    if coincidencia is None:
        return None
    return coincidencia.group(1) if coincidencia.groups() else coincidencia.group(0)


def valores_coinciden(extraido: str | None, esperado: str | None, tolerancia_digito_extra: bool = False) -> bool:
    """Compara dos valores numericos (o cualquier string) para la condicion
    de parada de repetir_hasta. Con tolerancia_digito_extra=True, dos
    valores coinciden tambien si uno es el otro mas un digito de mas al
    final (patron real de NIT: el sitio suele traer el digito de
    verificacion pegado, ej. 9004523301 para el NIT base 900452330)."""
    a = re.sub(r"\D", "", extraido or "")
    b = re.sub(r"\D", "", esperado or "")
    if not a or not b:
        return False
    if a == b:
        return True
    if tolerancia_digito_extra:
        return a.startswith(b) or b.startswith(a)
    return False
