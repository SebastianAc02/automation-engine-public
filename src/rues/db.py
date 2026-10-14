import sqlite3

from src.rues.modelos import ContactoRues, EmpresaObjetivo, TelefonoFuente

_SCHEMA = """
CREATE TABLE IF NOT EXISTS empresa_objetivo (
  id_empresa TEXT PRIMARY KEY,
  nombre_oficial TEXT,
  nombre_legal TEXT,
  usuarios REAL,
  procesada INTEGER NOT NULL DEFAULT 0,
  rues_error TEXT,
  estado_matricula TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS contacto_rues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  id_empresa TEXT NOT NULL,
  nombre TEXT, apellido TEXT, cargo TEXT, cargo_categoria TEXT,
  documento TEXT, es_rep_legal INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS telefono_fuente (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  id_empresa TEXT NOT NULL,
  fuente TEXT NOT NULL, numero TEXT, nit_pagina TEXT,
  tipo TEXT NOT NULL DEFAULT 'desconocido',
  nit_verificado INTEGER NOT NULL DEFAULT 0,
  match_dian INTEGER NOT NULL DEFAULT 0,
  supremamente_confirmado INTEGER NOT NULL DEFAULT 0,
  estado TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def conectar(ruta: str) -> sqlite3.Connection:
    con = sqlite3.connect(ruta)
    con.executescript(_SCHEMA)
    # migracion idempotente para bases del engine creadas antes de este campo
    columnas = {f[1] for f in con.execute("PRAGMA table_info(empresa_objetivo)")}
    if "estado_matricula" not in columnas:
        con.execute("ALTER TABLE empresa_objetivo ADD COLUMN estado_matricula TEXT")
        con.commit()
    return con


def guardar_objetivo(con: sqlite3.Connection, e: EmpresaObjetivo) -> None:
    con.execute(
        "INSERT OR IGNORE INTO empresa_objetivo (id_empresa, nombre_oficial, nombre_legal, usuarios) VALUES (?,?,?,?)",
        (e.id_empresa, e.nombre_oficial, e.nombre_legal, e.usuarios),
    )
    con.commit()


def guardar_contacto(con: sqlite3.Connection, id_empresa: str, c: ContactoRues) -> None:
    con.execute(
        "INSERT INTO contacto_rues (id_empresa, nombre, apellido, cargo, cargo_categoria, documento, es_rep_legal) "
        "VALUES (?,?,?,?,?,?,?)",
        (id_empresa, c.nombre, c.apellido, c.cargo, c.cargo_categoria, c.documento, int(c.es_rep_legal)),
    )
    con.commit()


def guardar_telefono(con: sqlite3.Connection, id_empresa: str, t: TelefonoFuente) -> None:
    con.execute(
        "INSERT INTO telefono_fuente "
        "(id_empresa, fuente, numero, nit_pagina, tipo, nit_verificado, match_dian, supremamente_confirmado, estado) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            id_empresa, t.fuente, t.numero, t.nit_pagina, t.tipo,
            int(t.nit_verificado), int(t.match_dian), int(t.supremamente_confirmado), t.estado,
        ),
    )
    con.commit()


def marcar_procesada(
    con: sqlite3.Connection, id_empresa: str, rues_error: str | None = None,
    estado_matricula: str | None = None,
) -> None:
    con.execute(
        "UPDATE empresa_objetivo SET procesada=1, rues_error=?, estado_matricula=?, "
        "updated_at=datetime('now') WHERE id_empresa=?",
        (rues_error, estado_matricula, id_empresa),
    )
    con.commit()
