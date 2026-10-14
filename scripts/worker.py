"""Worker de una slice: procesa sus NITs en orden, escribe su propia base del
engine (ENGINE_DB_PATH) y salta las ya procesadas para poder reanudar tras una
caida. Uso: python scripts/worker.py <slice_file>"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from config.settings import settings  # noqa: E402
from src.rues import db  # noqa: E402
from src.rues.objetivos import cargar_por_nit  # noqa: E402
from src.rues.runner import procesar_empresa  # noqa: E402

nits = [linea.strip() for linea in Path(sys.argv[1]).read_text().splitlines() if linea.strip()]

con = db.conectar(settings.engine_db_path)
hechas = {r[0] for r in con.execute("SELECT id_empresa FROM empresa_objetivo WHERE procesada=1")}
pendientes = [n for n in nits if n not in hechas]
logger.info(f"worker: {len(pendientes)} pendientes de {len(nits)} en la slice")

for empresa in cargar_por_nit(settings.prod_db_path, pendientes):
    try:
        db.guardar_objetivo(con, empresa)
        resultado = procesar_empresa(empresa)
        for contacto in resultado.contactos:
            db.guardar_contacto(con, empresa.id_empresa, contacto)
        for tel in resultado.telefonos:
            db.guardar_telefono(con, empresa.id_empresa, tel)
        db.marcar_procesada(con, empresa.id_empresa, resultado.rues_error, resultado.estado_matricula)
        if resultado.estado_matricula and resultado.estado_matricula != "ACTIVA":
            logger.warning(f"{empresa.id_empresa}: estado_matricula={resultado.estado_matricula!r}")
        conf = [t for t in resultado.telefonos if t.supremamente_confirmado]
        logger.info(
            f"{empresa.id_empresa}: {len(resultado.contactos)}c, {len(conf)} conf, "
            f"fuentes={[t.fuente for t in conf]}"
        )
    except Exception as error:
        logger.error(f"{empresa.id_empresa}: FALLO no capturado, se salta: {error!r}")
        continue
con.close()
