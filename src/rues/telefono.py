from loguru import logger

from config.settings import settings
from src.ejecutores.camoufox import CamoufoxEjecutor
from src.engine import cargar_receta
from src.rues.modelos import TelefonoFuente


def buscar_dian(cedula: str, headless: bool = True) -> TelefonoFuente:
    # Un solo intento, sin reintentos: dian dispara la recuperacion de clave real
    # de una persona y la DIAN rate-limitea si se golpea la misma cedula repetido
    # (aviso del propio recetas/dian.yaml). Nunca en loop contra la misma cedula.
    receta = cargar_receta(str(settings.dir_recetas / "dian.yaml"))
    receta.headless = headless
    try:
        resultado = CamoufoxEjecutor().ejecutar(receta, {"cedula": cedula})
    except Exception as e:
        logger.warning(f"dian cc={cedula}: excepcion no capturada por el ejecutor: {e!r}")
        return TelefonoFuente(fuente="dian", estado="no_encontrado")

    if not resultado.exito:
        # fallo un paso del flujo (selector, timeout, pantalla inesperada): no
        # es necesariamente que la DIAN no tenga la cedula, puede ser el
        # scraper roto. Se loguea el diagnostico completo para diferenciar.
        logger.warning(f"dian cc={cedula}: fallo en el flujo, no es necesariamente 'no existe'.\n{resultado.error}")
        return TelefonoFuente(fuente="dian", estado="no_encontrado")

    valor = next((v for v in resultado.datos.values() if v), None)
    if not valor:
        logger.warning(f"dian cc={cedula}: el flujo termino sin error pero no extrajo ningun valor")
        return TelefonoFuente(fuente="dian", estado="no_encontrado")
    return TelefonoFuente(fuente="dian", numero=valor, estado="ok")
