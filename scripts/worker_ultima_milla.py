"""Workers de la ultima milla: toman links de la cola, piden el PDF completo
al servicio de descarga, lo leen con regex puro (sin LLM) buscando el
patron de celular colombiano, y marcan la fila. Borran el PDF apenas lo
procesan.

Concurrencia: N workers en hilos, cada uno reclama filas de forma atomica
(BEGIN IMMEDIATE + UPDATE), asi que dos workers nunca agarran el mismo
link. Si hay varios puertos de servicio configurados, cada worker usa uno
distinto (round-robin) para que las descargas sean paralelas de verdad;
con un solo puerto quedan en fila dentro del servicio.

Uso: python scripts/worker_ultima_milla.py [n_workers] [puertos_csv]
  ej: python scripts/worker_ultima_milla.py 4 5055,5056,5057,5058
"""
import json
import os
import sqlite3
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from src.flujos.scribd import (  # noqa: E402
    _PATRON_CELULAR_CO,
    _descargar_via_servicio,
    _extraer_texto_pdf,
)

RUTA_COLA = str(Path(__file__).resolve().parent.parent / "cola_ultima_milla.db")
N_WORKERS = int(sys.argv[1]) if len(sys.argv) > 1 else 4
PUERTOS = (sys.argv[2].split(",") if len(sys.argv) > 2 else ["5055"])
_lock = threading.Lock()


def _con():
    con = sqlite3.connect(RUTA_COLA, timeout=60)
    con.isolation_level = None
    con.execute("PRAGMA busy_timeout=60000")
    return con


def reclamar(con, worker: str):
    """Toma una fila pendiente de forma atomica. Devuelve la fila o None."""
    con.execute("BEGIN IMMEDIATE")
    try:
        fila = con.execute(
            "SELECT id,id_empresa,documento,persona,ultimos4,doc_id,url FROM cola "
            "WHERE estado='pendiente' ORDER BY id LIMIT 1"
        ).fetchone()
        if fila is None:
            con.execute("COMMIT")
            return None
        con.execute(
            "UPDATE cola SET estado='procesando', worker=?, intentos=intentos+1, "
            "updated_at=datetime('now') WHERE id=?", (worker, fila[0]))
        con.execute("COMMIT")
        return fila
    except Exception:
        con.execute("ROLLBACK")
        raise


def procesar(fila, servicio_url: str) -> dict:
    _id, nit, doc, persona, ultimos4, doc_id, url = fila
    ruta = _descargar_via_servicio(url, servicio_url)
    if not ruta:
        return {"id": _id, "estado": "fallido", "error": "el servicio no devolvio PDF"}
    try:
        texto = _extraer_texto_pdf(ruta)
        numeros = sorted(set(_PATRON_CELULAR_CO.findall(texto)))
        hay = bool(ultimos4) and any(n.endswith(ultimos4) for n in numeros)
        return {"id": _id, "estado": "hecho", "numeros": numeros, "hay_match": hay,
                "documento": doc, "persona": persona, "id_empresa": nit, "url": url}
    except Exception as e:
        return {"id": _id, "estado": "fallido", "error": repr(e)}
    finally:
        try:
            os.remove(ruta)   # limpieza obligatoria, no acumular PDFs en disco
        except OSError:
            pass


def consolidar(con, documento: str):
    """Cuando ya no queda nada pendiente de esa cedula, junta todo lo que
    salio de sus documentos y lo reporta como un solo resultado."""
    quedan = con.execute(
        "SELECT COUNT(*) FROM cola WHERE documento=? AND estado IN ('pendiente','procesando')",
        (documento,)).fetchone()[0]
    if quedan:
        return None
    filas = con.execute(
        "SELECT id_empresa,persona,ultimos4,numeros,hay_match,url,estado FROM cola WHERE documento=?",
        (documento,)).fetchall()
    todos, matches = set(), []
    for nit, persona, u4, nums, hay, url, estado in filas:
        for n in json.loads(nums or "[]"):
            todos.add(n)
            if hay and u4 and n.endswith(u4):
                matches.append({"numero": n, "documento": url})
    res = {"documento": documento, "id_empresa": filas[0][0], "persona": filas[0][1],
           "ultimos4": filas[0][2], "docs_procesados": len(filas),
           "numeros_vistos": sorted(todos), "coincidencias": matches,
           "fallidos": sum(1 for f in filas if f[6] == "fallido")}
    logger.info(
        f"CONSOLIDADO cc={documento} {res['persona'][:30]}: {res['docs_procesados']} docs, "
        f"{len(todos)} numeros vistos, {len(matches)} MATCH")
    return res


def worker(indice: int):
    nombre = f"w{indice}"
    servicio = f"http://localhost:{PUERTOS[indice % len(PUERTOS)]}"
    con = _con()
    while True:
        with _lock:
            fila = reclamar(con, nombre)
        if fila is None:
            break
        res = procesar(fila, servicio)
        with _lock:
            con.execute("BEGIN IMMEDIATE")
            if res["estado"] == "hecho":
                con.execute(
                    "UPDATE cola SET estado='hecho', numeros=?, hay_match=?, error=NULL, "
                    "updated_at=datetime('now') WHERE id=?",
                    (json.dumps(res["numeros"]), int(res["hay_match"]), res["id"]))
            else:
                con.execute(
                    "UPDATE cola SET estado='fallido', error=?, updated_at=datetime('now') WHERE id=?",
                    (res.get("error"), res["id"]))
            con.execute("COMMIT")
            final = consolidar(con, fila[2])
        if final and final["coincidencias"]:
            with open("resultados_ultima_milla.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(final, ensure_ascii=False) + "\n")
    con.close()


def main():
    con = _con()
    pend = con.execute("SELECT COUNT(*) FROM cola WHERE estado='pendiente'").fetchone()[0]
    con.close()
    logger.info(f"arrancando {N_WORKERS} workers sobre {pend} links pendientes, puertos={PUERTOS}")
    hilos = [threading.Thread(target=worker, args=(i,), daemon=False) for i in range(N_WORKERS)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    con = _con()
    for estado, n in con.execute("SELECT estado, COUNT(*) FROM cola GROUP BY estado"):
        logger.info(f"  {estado}: {n}")
    con.close()


if __name__ == "__main__":
    main()
