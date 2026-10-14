"""Pase de Scribd desde el Mac (Google, IP residencial). Lee una copia de la base
del engine del VPS (que trae las empresas con DIAN), busca por el nombre completo
del representante (instruccion del operador: site:scribd.com "nombre persona"),
con la empresa como respaldo si la persona no trae documentos. Matchea el celular
contra los 4 digitos de la DIAN y guarda match+candidatos. Pausas largas entre
empresas para no repetir el bloqueo de Google por volumen.
Uso: python scripts/scribd_mac.py <copia_engine_db_del_vps>"""
import random
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from config.settings import settings  # noqa: E402
from src.flujos.scribd import buscar_telefono_scribd  # noqa: E402
from src.rues import db as enginedb  # noqa: E402
from src.rues.modelos import EmpresaObjetivo, TelefonoFuente  # noqa: E402

_PAUSA_MIN_S = 60
_PAUSA_MAX_S = 100

fuente = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
fuente.row_factory = sqlite3.Row
filas = fuente.execute(
    "SELECT o.id_empresa, o.nombre_oficial, o.nombre_legal, "
    "       GROUP_CONCAT(DISTINCT t.numero) AS dians, "
    "       (SELECT nombre || ' ' || apellido FROM contacto_rues c "
    "        WHERE c.id_empresa=o.id_empresa "
    "        ORDER BY (cargo_categoria='rep_legal') DESC LIMIT 1) AS persona "
    "FROM empresa_objetivo o "
    "JOIN telefono_fuente t ON t.id_empresa=o.id_empresa "
    "     AND t.fuente='dian' AND t.numero IS NOT NULL "
    "GROUP BY o.id_empresa"
).fetchall()
fuente.close()

con = enginedb.conectar(settings.engine_db_path)
hechas = {r[0] for r in con.execute("SELECT id_empresa FROM empresa_objetivo WHERE procesada=1")}
pendientes = [f for f in filas if f["id_empresa"] not in hechas]
logger.info(f"scribd-mac: {len(pendientes)} empresas con DIAN pendientes de scribd (pausas {_PAUSA_MIN_S}-{_PAUSA_MAX_S}s)")


def _guardar(con, id_empresa, resultado):
    for m in resultado.get("coincidencias", []):
        enginedb.guardar_telefono(
            con, id_empresa,
            TelefonoFuente(fuente="scribd", numero=m["numero"], tipo="celular",
                           match_dian=True, supremamente_confirmado=True, estado="ok"),
        )
    for m in resultado.get("posibles", [])[:8]:
        enginedb.guardar_telefono(
            con, id_empresa,
            TelefonoFuente(fuente="scribd", numero=m["numero"], tipo="celular",
                           match_dian=False, supremamente_confirmado=False, estado="ok"),
        )


for i, f in enumerate(pendientes):
    empresa_nombre = f["nombre_legal"] or f["nombre_oficial"]
    persona = (f["persona"] or "").strip()
    ultimos4 = [d for d in (f["dians"] or "").split(",") if d]
    enginedb.guardar_objetivo(
        con, EmpresaObjetivo(id_empresa=f["id_empresa"], nombre_oficial=f["nombre_oficial"], nombre_legal=empresa_nombre)
    )
    try:
        total_match, total_cand = 0, 0
        # 1. Busqueda primaria: nombre completo de la persona (instruccion del operador)
        if persona:
            s = buscar_telefono_scribd(persona, ultimos4, headless=True)
            _guardar(con, f["id_empresa"], s)
            total_match += len(s.get("coincidencias", []))
            total_cand += len(s.get("posibles", []))
        # 2. Respaldo: si la persona no trajo nada, prueba por la empresa
        if total_match == 0 and total_cand == 0:
            time.sleep(random.uniform(15, 25))
            s2 = buscar_telefono_scribd(empresa_nombre, ultimos4, headless=True)
            _guardar(con, f["id_empresa"], s2)
            total_match += len(s2.get("coincidencias", []))
            total_cand += len(s2.get("posibles", []))
        logger.info(f"{f['id_empresa']} persona='{persona}': {total_match} match, {total_cand} candidatos")
    except Exception as error:
        logger.error(f"{f['id_empresa']} scribd fallo: {error!r}")
    enginedb.marcar_procesada(con, f["id_empresa"])

    if i < len(pendientes) - 1:
        pausa = random.uniform(_PAUSA_MIN_S, _PAUSA_MAX_S)
        logger.info(f"pausa {pausa:.0f}s antes de la siguiente")
        time.sleep(pausa)
con.close()
