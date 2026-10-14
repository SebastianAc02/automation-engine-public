"""Etapa 1 del pipeline (rues -> dian -> directorios -> scribd): corre la
receta rues_representante_legal.yaml sobre una lista de NIT, trae
representante legal + suplente con documento real, y lo guarda en su
propia base para que la siguiente etapa (dian) lea de ahi. No usa perfil
persistente de navegador, asi que es seguro paralelizar con hilos (cada
Camoufox() es su propio proceso de navegador aislado).
Uso: python scripts/rues_web_batch.py <archivo_nits.txt id_empresa por linea> [n_hilos]"""
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from config.settings import settings  # noqa: E402
from src.engine import cargar_receta  # noqa: E402
from src.ejecutores.camoufox import CamoufoxEjecutor  # noqa: E402

N_HILOS = int(sys.argv[2]) if len(sys.argv) > 2 else 4
ids = [ln.strip() for ln in Path(sys.argv[1]).read_text().splitlines() if ln.strip()]

ruta_db = str(Path(__file__).resolve().parent.parent / "rues_web_batch.db")
_lock_db = threading.Lock()


def _con():
    con = sqlite3.connect(ruta_db, timeout=30)
    con.execute(
        "CREATE TABLE IF NOT EXISTS contacto_rues_web ("
        " id_empresa TEXT, nombre TEXT, apellido TEXT, cargo TEXT, cargo_categoria TEXT,"
        " documento TEXT, es_rep_legal INTEGER, PRIMARY KEY (id_empresa, documento))"
    )
    con.execute("CREATE TABLE IF NOT EXISTS hecho (id_empresa TEXT PRIMARY KEY, error TEXT)")
    con.commit()
    return con


with _con() as con_inicial:
    hechas = {r[0] for r in con_inicial.execute("SELECT id_empresa FROM hecho")}
pendientes = [i for i in ids if i not in hechas]
logger.info(f"rues-web-batch: {len(pendientes)} pendientes de {len(ids)}, {N_HILOS} hilos en paralelo")

_receta_base = cargar_receta(str(settings.dir_recetas / "rues_representante_legal.yaml"))


_PATRONES_RED_TRANSITORIA = ("NS_ERROR_NET_EMPTY_RESPONSE", "Ver informaci")
_ESPERAS_REINTENTO = (8, 20, 40)  # segundos entre intentos, creciente


def _procesar(id_empresa: str) -> tuple[str, int, str | None]:
    ejecutor = CamoufoxEjecutor()
    resultado = None
    for intento, espera_previa in enumerate((3, *_ESPERAS_REINTENTO)):
        if espera_previa:
            time.sleep(espera_previa)
        resultado = ejecutor.ejecutar(_receta_base, {"nit": id_empresa})
        if resultado.exito:
            break
        # solo reintenta si el error tiene pinta de bloqueo transitorio de
        # red (rues.org.co tira NS_ERROR_NET_EMPTY_RESPONSE incluso en
        # secuencial, con apenas unos segundos entre peticiones); un error
        # de otro tipo (selector roto, LLM, etc.) no se beneficia de
        # reintentar y se deja fallar de una vez.
        if not any(p in (resultado.error or "") for p in _PATRONES_RED_TRANSITORIA):
            break
        logger.info(f"{id_empresa}: fallo de red transitorio, reintento {intento + 1}/{len(_ESPERAS_REINTENTO)}")

    if not resultado.exito:
        return id_empresa, 0, resultado.error

    representantes = resultado.datos.get("representantes")
    contactos = representantes.get("contactos", []) if isinstance(representantes, dict) else []

    with _lock_db:
        con = _con()
        try:
            for c in contactos:
                con.execute(
                    "INSERT OR REPLACE INTO contacto_rues_web "
                    "(id_empresa, nombre, apellido, cargo, cargo_categoria, documento, es_rep_legal) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (id_empresa, c.get("nombre"), c.get("apellido"), c.get("cargo"),
                     c.get("cargo_categoria"), c.get("documento"), int(c.get("es_rep_legal", False))),
                )
            con.execute("INSERT OR REPLACE INTO hecho (id_empresa, error) VALUES (?, NULL)", (id_empresa,))
            con.commit()
        finally:
            con.close()

    return id_empresa, len(contactos), None


confirmadas = 0
with ThreadPoolExecutor(max_workers=N_HILOS) as pool:
    futuros = {pool.submit(_procesar, i): i for i in pendientes}
    for futuro in as_completed(futuros):
        id_empresa = futuros[futuro]
        try:
            _id, n_contactos, error = futuro.result()
        except Exception as e:
            logger.warning(f"{id_empresa}: EXCEPCION NO MANEJADA -> {e!r}")
            with _lock_db:
                con = _con()
                con.execute("INSERT OR REPLACE INTO hecho (id_empresa, error) VALUES (?,?)", (id_empresa, repr(e)))
                con.commit()
                con.close()
            continue

        if error:
            logger.warning(f"{id_empresa}: FALLO -> {error[:300]!r}")
            with _lock_db:
                con = _con()
                con.execute("INSERT OR REPLACE INTO hecho (id_empresa, error) VALUES (?,?)", (id_empresa, error))
                con.commit()
                con.close()
        elif n_contactos == 0:
            logger.info(f"{id_empresa}: sin contactos (pagina sin info o 'Informacion no disponible')")
        else:
            confirmadas += 1
            logger.info(f"{id_empresa}: {n_contactos} contacto(s) guardado(s)")

logger.info(f"=== fin: {confirmadas}/{len(pendientes)} empresas con al menos 1 contacto en esta corrida ===")
