"""Toma las empresas que dian_repaso.py acaba de resolver (ultimos4 en su
propia base, no en produccion todavia) y les corre directorios + scribd.
No reconcilia nada a produccion: solo junta candidatos en su propia base.
Uso: python scripts/directorios_desde_dian_repaso.py <dian_repaso.db>"""
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from config.settings import settings  # noqa: E402
from src.flujos import directorio, scribd  # noqa: E402
from src.rues import db as enginedb  # noqa: E402
from src.rues.modelos import TelefonoFuente, match_ultimos4, tipo_numero  # noqa: E402

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


ruta_dian_db = sys.argv[1]
con_dian = sqlite3.connect(ruta_dian_db)
pares = con_dian.execute(
    "SELECT id_empresa, numero FROM telefono_fuente WHERE fuente='dian' AND numero IS NOT NULL"
).fetchall()
con_dian.close()
logger.info(f"{len(pares)} empresas con ultimos4 de la DIAN para procesar")

con = enginedb.conectar(str(Path(__file__).resolve().parent.parent / "directorios_desde_dian.db"))
con.execute("CREATE TABLE IF NOT EXISTS hecho (id_empresa TEXT PRIMARY KEY)")
con.commit()
hechas = {r[0] for r in con.execute("SELECT id_empresa FROM hecho")}
pendientes = [(e, u) for e, u in pares if e not in hechas]
logger.info(f"{len(pendientes)} pendientes de {len(pares)}")

prod_ro = sqlite3.connect(f"file:{settings.prod_db_path}?mode=ro", uri=True)

confirmadas = 0
for id_empresa, ultimo4 in pendientes:
    fila = prod_ro.execute(
        "SELECT nombre_legal, nombre_oficial FROM empresa WHERE id_empresa=?", (id_empresa,)
    ).fetchone()
    if not fila:
        logger.warning(f"{id_empresa}: no encontrada en produccion, se salta")
        con.execute("INSERT OR REPLACE INTO hecho (id_empresa) VALUES (?)", (id_empresa,))
        con.commit()
        continue
    nombre = fila[0] or fila[1]
    ultimos4 = [ultimo4]

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

    if not os.environ.get("RUES_SKIP_SCRIBD") and not any(t.supremamente_confirmado for t in encontrados):
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

            # ultima milla: si scribd (via el embed gratis) no confirmo nada,
            # se intenta con el servicio de descarga completa del operador
            # (bypass del paywall de ~4 paginas). Solo si el servicio esta
            # arriba (SCRIBD_SERVICIO_URL, default localhost:5055); si no
            # responde, se salta sin ensuciar el log con reintentos inutiles.
            pendiente_ultima_milla = s.get("_ultima_milla")
            if pendiente_ultima_milla and not any(t.supremamente_confirmado for t in encontrados):
                servicio_url = os.environ.get("SCRIBD_SERVICIO_URL", "http://localhost:5055")
                import httpx as _httpx
                try:
                    _httpx.get(servicio_url, timeout=3)
                    servicio_arriba = True
                except Exception:
                    servicio_arriba = False
                if servicio_arriba:
                    um = scribd.ultima_milla_scribd(
                        pendiente_ultima_milla["urls_no_confirmadas"], ultimos4, servicio_url
                    )
                    logger.info(
                        f"{id_empresa} ultima_milla: {um['documentos_intentados']} intentados, "
                        f"{len(um.get('coincidencias', []))} match"
                    )
                    for m in um.get("coincidencias", []):
                        t = TelefonoFuente(
                            fuente="scribd_pdf_completo", numero=m["numero"], tipo="celular",
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
