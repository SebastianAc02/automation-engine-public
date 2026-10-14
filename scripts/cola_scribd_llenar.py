"""Llena la cola de la ultima milla: por cada persona pendiente, corre las
6 busquedas de scribd (3 motores x 2 variantes), deduplica por doc_id y
guarda CADA link como una fila de cola con su id, atada a la cedula de esa
persona. No descarga nada aca: eso lo hacen los workers.

La cola es persistente a proposito: si el proceso se cae, los links ya
recolectados no se pierden y los workers siguen donde iban.

Uso: python scripts/cola_scribd_llenar.py <archivo.json con la lista de personas>
Cada item: {"id_empresa","documento","persona","ultimos4"}
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from camoufox.sync_api import Camoufox  # noqa: E402
from loguru import logger  # noqa: E402

from config.settings import settings  # noqa: E402
from src.ejecutores.camoufox import opciones_camoufox  # noqa: E402
from src.flujos.scribd import (  # noqa: E402
    _PATRON_ID_SCRIBD,
    _PERFIL_GOOGLE,
    _recolectar_scribd_con_snippet,
)

RUTA_COLA = str(Path(__file__).resolve().parent.parent / "cola_ultima_milla.db")

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS cola (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  id_empresa  TEXT NOT NULL,
  documento   TEXT,
  persona     TEXT,
  ultimos4    TEXT,
  doc_id      TEXT NOT NULL,
  url         TEXT NOT NULL,
  estado      TEXT NOT NULL DEFAULT 'pendiente',
  worker      TEXT,
  numeros     TEXT,
  hay_match   INTEGER NOT NULL DEFAULT 0,
  error       TEXT,
  intentos    INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT,
  UNIQUE(documento, doc_id)
);
CREATE INDEX IF NOT EXISTS ix_cola_estado ON cola(estado);
CREATE INDEX IF NOT EXISTS ix_cola_doc ON cola(documento);
CREATE TABLE IF NOT EXISTS recolectada (documento TEXT PRIMARY KEY, links INTEGER, created_at TEXT DEFAULT (datetime('now')));
"""


def conectar():
    con = sqlite3.connect(RUTA_COLA, timeout=30)
    con.executescript(_ESQUEMA)
    con.commit()
    return con


def main():
    personas = json.load(open(sys.argv[1], encoding="utf-8"))
    con = conectar()
    ya = {r[0] for r in con.execute("SELECT documento FROM recolectada")}
    pendientes = [p for p in personas if p.get("documento") and p["documento"] not in ya]
    logger.info(f"recolectar links para {len(pendientes)} personas (de {len(personas)})")

    opciones = opciones_camoufox(True, perfil=_PERFIL_GOOGLE, proxy=settings.camoufox_proxy or None)
    with Camoufox(**opciones) as contexto:
        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
        for p in pendientes:
            try:
                encontrados = _recolectar_scribd_con_snippet(pagina, contexto, p["persona"])
            except Exception as e:
                logger.warning(f"{p['documento']} {p['persona']}: fallo la recoleccion -> {e!r}")
                continue

            insertados = 0
            for url, _snippet in encontrados:
                m = _PATRON_ID_SCRIBD.search(url)
                if not m:
                    continue
                try:
                    con.execute(
                        "INSERT OR IGNORE INTO cola (id_empresa,documento,persona,ultimos4,doc_id,url) "
                        "VALUES (?,?,?,?,?,?)",
                        (p["id_empresa"], p["documento"], p["persona"], p.get("ultimos4"), m.group(1), url),
                    )
                    insertados += con.total_changes and 1 or 0
                except sqlite3.Error as e:
                    logger.warning(f"insert fallo: {e!r}")
            con.execute("INSERT OR REPLACE INTO recolectada (documento,links) VALUES (?,?)",
                        (p["documento"], len(encontrados)))
            con.commit()
            logger.info(f"{p['documento']} {p['persona'][:34]:34} -> {len(encontrados)} links en cola")

    total = con.execute("SELECT COUNT(*) FROM cola WHERE estado='pendiente'").fetchone()[0]
    logger.info(f"=== cola lista: {total} links pendientes de procesar ===")
    con.close()


if __name__ == "__main__":
    main()
