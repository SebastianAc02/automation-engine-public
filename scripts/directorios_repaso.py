"""Repasa directorios (informacolombia/portafolio/einforma) + scribd sobre
empresas que YA tienen DIAN (4 digitos) pero no numero completo confirmado.
No repite RUES ni DIAN. Corre via proxy (CAMOUFOX_PROXY) para que los
directorios no den timeout por la IP del datacenter.
Uso: python scripts/directorios_repaso.py <archivo_ids.txt id_empresa por linea>"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from config.settings import settings  # noqa: E402
from src.flujos import directorio, scribd  # noqa: E402
from src.rues import db as enginedb  # noqa: E402
from src.rues.modelos import EmpresaObjetivo, TelefonoFuente, match_ultimos4, tipo_numero  # noqa: E402
from src.rues.objetivos import cargar_por_nit  # noqa: E402

_DIRECTORIOS = [
    ("informacolombia", directorio.buscar_empresa_informacolombia),
    ("portafolio", directorio.buscar_empresa_portafolio),
    ("einforma", directorio.buscar_empresa_einforma),
]


def _numeros_directorio(res: dict):
    if res.get("encontrado") and res.get("telefono"):
        return [(res["telefono"], True, res.get("nit"))]
    return [(c["telefono"], False, c.get("nit")) for c in res.get("candidatos", []) if c.get("telefono")]


def _clasificar(fuente, numero, nit_verificado, nit_pagina, ultimos4):
    tipo = tipo_numero(numero)
    md = match_ultimos4(numero, ultimos4)
    return TelefonoFuente(
        fuente=fuente, numero=numero, nit_pagina=nit_pagina, tipo=tipo,
        nit_verificado=nit_verificado, match_dian=md,
        supremamente_confirmado=(tipo == "celular" and md), estado="ok",
    )


ids = [ln.strip() for ln in Path(sys.argv[1]).read_text().splitlines() if ln.strip()]
con = enginedb.conectar(str(Path(__file__).resolve().parent.parent / "directorios_repaso.db"))
con.execute("CREATE TABLE IF NOT EXISTS hecho (id_empresa TEXT PRIMARY KEY)")
con.commit()
hechas = {r[0] for r in con.execute("SELECT id_empresa FROM hecho")}
pendientes = [i for i in ids if i not in hechas]
logger.info(f"directorios-repaso: {len(pendientes)} pendientes de {len(ids)}")

empresas = {e.id_empresa: e for e in cargar_por_nit(settings.prod_db_path, pendientes)}

import sqlite3  # noqa: E402
prod_ro = sqlite3.connect(f"file:{settings.prod_db_path}?mode=ro", uri=True)

confirmadas = 0
for id_empresa in pendientes:
    empresa = empresas.get(id_empresa)
    if not empresa:
        logger.warning(f"{id_empresa}: no encontrada en produccion, se salta")
        con.execute("INSERT OR REPLACE INTO hecho (id_empresa) VALUES (?)", (id_empresa,))
        con.commit()
        continue
    nombre = empresa.nombre_legal or empresa.nombre_oficial
    ultimos4 = [
        r[0] for r in prod_ro.execute(
            "SELECT numero FROM empresa_telefono WHERE id_empresa=? AND fuente='dian' AND numero IS NOT NULL",
            (id_empresa,),
        ).fetchall()
    ]

    encontrados = []
    for fuente, funcion in _DIRECTORIOS:
        try:
            res = funcion(nombre, id_empresa, headless=True)
        except Exception as error:
            logger.warning(f"{id_empresa} {fuente} fallo: {error!r}")
            continue
        for numero, nit_ver, nit_pag in _numeros_directorio(res):
            t = _clasificar(fuente, numero, nit_ver, nit_pag, ultimos4)
            encontrados.append(t)
            enginedb.guardar_telefono(con, id_empresa, t)

    if ultimos4 and not os.environ.get("RUES_SKIP_SCRIBD") and not any(t.supremamente_confirmado for t in encontrados):
        try:
            s = scribd.buscar_telefono_scribd(nombre, ultimos4, headless=True)
            logger.info(
                f"{id_empresa} scribd: {s['documentos_revisados']} documentos revisados, "
                f"{len(s.get('coincidencias', []))} match, {len(s.get('posibles', []))} candidatos"
            )
            for m in s.get("coincidencias", []):
                t = TelefonoFuente(
                    fuente="scribd", numero=m["numero"], tipo="celular",
                    match_dian=True, supremamente_confirmado=True, estado="ok",
                )
                encontrados.append(t)
                enginedb.guardar_telefono(con, id_empresa, t)
        except Exception as error:
            logger.warning(f"{id_empresa} scribd fallo: {error!r}")

    sup = [t for t in encontrados if t.supremamente_confirmado]
    if sup:
        confirmadas += 1
        logger.info(f"{id_empresa} {nombre}: CONFIRMADO {[t.numero for t in sup]} via {[t.fuente for t in sup]}")
    else:
        logger.info(f"{id_empresa} {nombre}: {len(encontrados)} candidatos, 0 confirmados")

    con.execute("INSERT OR REPLACE INTO hecho (id_empresa) VALUES (?)", (id_empresa,))
    con.commit()

logger.info(f"=== fin: {confirmadas}/{len(pendientes)} confirmadas en esta corrida ===")
con.close()
