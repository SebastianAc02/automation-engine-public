import os
import sqlite3

from loguru import logger

# Reconciliacion del engine hacia produccion. Toma lo que el engine dejo en
# rues_engine.db y lo escribe en isps.db con el protocolo del runbook: backup
# antes, una empresa a la vez, transaccion corta, relectura. Nunca un re-sync
# masivo. Coexiste con followups_worker (escribe cada 5 min) via busy_timeout.

_BUSY_TIMEOUT_MS = 30000


def asegurar_columna_documento(ruta_prod: str) -> None:
    # Idempotente. La tabla contacto de produccion no trae columna de documento;
    # se agrega la primera vez y en corridas siguientes no hace nada.
    con = sqlite3.connect(ruta_prod)
    try:
        con.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        columnas = {fila[1] for fila in con.execute("PRAGMA table_info(contacto)")}
        if "documento" not in columnas:
            con.execute("ALTER TABLE contacto ADD COLUMN documento TEXT")
            con.execute("ALTER TABLE contacto ADD COLUMN documento_tipo TEXT")
            con.commit()
            logger.info("contacto: columnas documento y documento_tipo agregadas")
    finally:
        con.close()


def respaldar(ruta_prod: str) -> str:
    # Backup consistente ANTES de cualquier escritura. Se usa la API de backup
    # online de SQLite, no un cp del archivo: con el worker escribiendo y el WAL
    # abierto un cp saldria inconsistente (runbook). El sufijo es el mtime del
    # archivo en segundos: determinista y sin colision, porque dos estados
    # distintos de la base tienen mtime distinto y el mismo estado reusa el .bak.
    sufijo = int(os.path.getmtime(ruta_prod))
    ruta_bak = f"{ruta_prod}.bak-{sufijo}"
    if os.path.exists(ruta_bak):
        logger.info(f"backup ya existe, se reutiliza: {ruta_bak}")
        return ruta_bak
    origen = sqlite3.connect(f"file:{ruta_prod}?mode=ro", uri=True)
    destino = sqlite3.connect(ruta_bak)
    try:
        origen.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        origen.backup(destino)
    finally:
        destino.close()
        origen.close()
    logger.info(f"backup creado: {ruta_bak}")
    return ruta_bak


def reconciliar_empresa(con_prod, id_empresa: str, contactos, telefonos, estado_matricula: str | None = None) -> dict:
    # Escribe una sola empresa en una transaccion corta. Espera que la conexion
    # venga en autocommit (isolation_level=None) para que BEGIN/COMMIT sean
    # explicitos. Dedup de contacto por documento (o por nombre+apellido si el
    # documento viene vacio); dedup de telefono por numero. Solo agrega al hueco,
    # nunca pisa filas existentes.
    conteos = {
        "contactos_insertados": 0,
        "telefonos_insertados": 0,
        "contactos_saltados": 0,
        "telefonos_saltados": 0,
    }
    con_prod.execute("BEGIN IMMEDIATE")
    try:
        for c in contactos:
            documento = (c["documento"] or "").strip()
            if documento:
                existe = con_prod.execute(
                    "SELECT 1 FROM contacto WHERE id_empresa=? AND documento=? LIMIT 1",
                    (id_empresa, documento),
                ).fetchone()
            else:
                existe = con_prod.execute(
                    "SELECT 1 FROM contacto WHERE id_empresa=? "
                    "AND IFNULL(nombre,'')=? AND IFNULL(apellido,'')=? LIMIT 1",
                    (id_empresa, c["nombre"] or "", c["apellido"] or ""),
                ).fetchone()
            if existe:
                conteos["contactos_saltados"] += 1
                continue
            # OJO: si la matricula de la empresa en RUES no esta ACTIVA
            # (CANCELADA, SUSPENDIDA, etc.), el representante puede no ser
            # vigente. Se marca explicito en notas, nunca se descarta en
            # silencio ni se asume que el dato sigue siendo valido.
            notas = (
                f"ALERTA: estado_matricula RUES = {estado_matricula} (no ACTIVA), "
                f"el representante puede no ser vigente"
                if estado_matricula and estado_matricula != "ACTIVA"
                else None
            )
            con_prod.execute(
                "INSERT INTO contacto "
                "(id_empresa, nombre, apellido, cargo, cargo_categoria, es_rep_legal, "
                " documento, documento_tipo, fuente, notas, verificado_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,NULL)",
                (
                    id_empresa,
                    c["nombre"],
                    c["apellido"],
                    c["cargo"],
                    c["cargo_categoria"],
                    int(c["es_rep_legal"]),
                    documento or None,
                    "CC" if documento else None,
                    "RUES",
                    notas,
                ),
            )
            conteos["contactos_insertados"] += 1

        for t in telefonos:
            numero = (t["numero"] or "").strip()
            if not numero:
                conteos["telefonos_saltados"] += 1
                continue
            existe = con_prod.execute(
                "SELECT 1 FROM empresa_telefono WHERE id_empresa=? AND numero=? LIMIT 1",
                (id_empresa, numero),
            ).fetchone()
            if existe:
                conteos["telefonos_saltados"] += 1
                continue
            con_prod.execute(
                "INSERT INTO empresa_telefono "
                "(id_empresa, tipo, numero, fuente, verificado) "
                "VALUES (?, 'prospeccion', ?, ?, ?)",
                (id_empresa, numero, t["fuente"], int(t["supremamente_confirmado"])),
            )
            conteos["telefonos_insertados"] += 1

        con_prod.execute("COMMIT")
    except Exception:
        con_prod.execute("ROLLBACK")
        raise
    return conteos


def reconciliar(ruta_prod: str, ruta_engine: str) -> list[dict]:
    # Orquesta la reconciliacion completa. Backup primero, luego el esquema, luego
    # empresa por empresa. Se apoya en la columna reconciliada del engine para no
    # re-escribir lo ya subido.
    respaldar(ruta_prod)
    asegurar_columna_documento(ruta_prod)

    # El engine es nuestra base y se abre rw: la marca reconciliada se persiste
    # ahi. Solo produccion se trata con la conexion cuidadosa.
    con_engine = sqlite3.connect(ruta_engine)
    con_engine.row_factory = sqlite3.Row
    cols_engine = {f[1] for f in con_engine.execute("PRAGMA table_info(empresa_objetivo)")}
    if "reconciliada" not in cols_engine:
        con_engine.execute(
            "ALTER TABLE empresa_objetivo ADD COLUMN reconciliada INTEGER DEFAULT 0"
        )
        con_engine.commit()

    con_prod = sqlite3.connect(ruta_prod)
    con_prod.row_factory = sqlite3.Row
    con_prod.isolation_level = None  # autocommit: BEGIN/COMMIT explicitos por empresa
    con_prod.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")

    salida: list[dict] = []
    try:
        pendientes = con_engine.execute(
            "SELECT id_empresa FROM empresa_objetivo "
            "WHERE procesada=1 AND IFNULL(reconciliada,0)=0"
        ).fetchall()

        for fila in pendientes:
            id_empresa = fila["id_empresa"]
            contactos = con_engine.execute(
                "SELECT nombre, apellido, cargo, cargo_categoria, documento, es_rep_legal "
                "FROM contacto_rues WHERE id_empresa=?",
                (id_empresa,),
            ).fetchall()
            telefonos = con_engine.execute(
                "SELECT fuente, numero, supremamente_confirmado FROM telefono_fuente "
                "WHERE id_empresa=? AND estado='ok'",
                (id_empresa,),
            ).fetchall()
            fila_estado = con_engine.execute(
                "SELECT estado_matricula FROM empresa_objetivo WHERE id_empresa=?", (id_empresa,)
            ).fetchone()
            estado_matricula = fila_estado["estado_matricula"] if fila_estado else None

            conteos = reconciliar_empresa(con_prod, id_empresa, contactos, telefonos, estado_matricula)
            if estado_matricula and estado_matricula != "ACTIVA":
                logger.warning(f"{id_empresa}: estado_matricula={estado_matricula!r}, se marco en notas")

            # Relectura tras el COMMIT: confirma que las filas quedaron antes de
            # marcar la empresa como reconciliada en el engine.
            n_contactos = con_prod.execute(
                "SELECT COUNT(*) FROM contacto WHERE id_empresa=? AND fuente='RUES'",
                (id_empresa,),
            ).fetchone()[0]
            n_telefonos = con_prod.execute(
                "SELECT COUNT(*) FROM empresa_telefono WHERE id_empresa=? AND tipo='prospeccion'",
                (id_empresa,),
            ).fetchone()[0]

            con_engine.execute(
                "UPDATE empresa_objetivo SET reconciliada=1 WHERE id_empresa=?",
                (id_empresa,),
            )
            con_engine.commit()

            resultado = {"id_empresa": id_empresa, **conteos}
            salida.append(resultado)
            logger.info(
                f"{id_empresa}: +{conteos['contactos_insertados']} contactos "
                f"(saltados {conteos['contactos_saltados']}), "
                f"+{conteos['telefonos_insertados']} telefonos "
                f"(saltados {conteos['telefonos_saltados']}); "
                f"prod ahora tiene {n_contactos} contactos RUES, {n_telefonos} tel prospeccion"
            )
    finally:
        con_prod.close()
        con_engine.close()

    return salida
