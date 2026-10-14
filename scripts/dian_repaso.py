"""Repasa DIAN, solo DIAN, sobre empresas que ya tienen contacto+cedula pero
quedaron 'no_encontrado' (casi siempre por la IP del VPS). Corre desde el Mac
(IP residencial), un intento por cedula (sin loop, receta lo pide asi), guarda
en una base propia y al final reconcilia a produccion.
Uso: python scripts/dian_repaso.py <archivo_pendientes.txt id_empresa|cedula>"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from config.settings import settings  # noqa: E402
from src.rues import db as enginedb  # noqa: E402
from src.rues.telefono import buscar_dian  # noqa: E402

pares = []
for linea in Path(sys.argv[1]).read_text().splitlines():
    linea = linea.strip()
    if not linea:
        continue
    id_empresa, cedula = linea.split("|")
    pares.append((id_empresa, cedula))

engine_path = str(Path(__file__).resolve().parent.parent / "dian_repaso.db")
con = enginedb.conectar(engine_path)
con.execute(
    "CREATE TABLE IF NOT EXISTS repaso_hecho (id_empresa TEXT PRIMARY KEY, procesada INTEGER DEFAULT 0)"
)
con.commit()
hechas = {r[0] for r in con.execute("SELECT id_empresa FROM repaso_hecho WHERE procesada=1")}
pendientes = [(e, c) for e, c in pares if e not in hechas]
logger.info(f"dian-repaso: {len(pendientes)} pendientes de {len(pares)}")

recuperadas = 0
for id_empresa, cedula in pendientes:
    t = buscar_dian(cedula)
    if t.numero:
        enginedb.guardar_telefono(con, id_empresa, t)
        recuperadas += 1
        logger.info(f"{id_empresa} cc={cedula}: RECUPERADO {t.numero}")
    else:
        logger.info(f"{id_empresa} cc={cedula}: sigue sin dian")
    con.execute(
        "INSERT OR REPLACE INTO repaso_hecho (id_empresa, procesada) VALUES (?,1)", (id_empresa,)
    )
    con.commit()

logger.info(f"=== fin: {recuperadas}/{len(pendientes)} recuperadas en esta corrida ===")
con.close()
