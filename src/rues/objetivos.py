import sqlite3

from src.rues.modelos import EmpresaObjetivo

# Universo objetivo: ISP con NIT, sin telefono confirmado, excluyendo carriers,
# corporativo grande, no-ISP, utility, extranjero, SAE Plus (via flags de
# empresa_clasificacion) e Integra (via crm_software). Orden por tamano desc.
_SQL_BASE = """
SELECT e.id_empresa,
       e.nombre_oficial,
       COALESCE(e.nombre_legal, e.nombre_oficial) AS nombre_legal,
       u.usuarios_efectivos
FROM empresa e
LEFT JOIN empresa_clasificacion c ON c.id_empresa = e.id_empresa
LEFT JOIN empresa_usuarios u ON u.id_empresa = e.id_empresa
WHERE e.tipo_id = 'nit'
  AND COALESCE(c.es_carrier,0)+COALESCE(c.es_corporativo_grande,0)
     +COALESCE(c.es_utility_no_isp,0)+COALESCE(c.es_no_isp_confirmado,0)
     +COALESCE(c.es_extranjero,0)+COALESCE(c.alianza_sae_plus,0) = 0
  -- Integra y SAE completos (flag de alianza + los que la usan como CRM/pasarela)
  AND COALESCE(e.crm_software,'') NOT IN ('Integra', 'Saeplus')
  AND COALESCE(e.pasarela_actual,'') NOT LIKE '%SAE%'
  -- EMCALI: ESP municipal, no es ISP (decision del operador 2026-09-03)
  AND e.id_empresa <> '890399003'
  -- clientes fuera: si ya es cliente no se enriquece (operador 2026-09-03)
  AND COALESCE(e.es_cliente,0) = 0
  AND NOT EXISTS (
        SELECT 1 FROM empresa_telefono t
        WHERE t.id_empresa = e.id_empresa AND t.verificado = 1)
"""

_ORDEN = "ORDER BY u.usuarios_efectivos DESC NULLS LAST, e.id_empresa ASC\nLIMIT ?"


def seleccionar_batch(
    ruta_prod: str, limite: int, excluidos: set[str] | None = None
) -> list[EmpresaObjetivo]:
    excluidos = excluidos or set()
    sql = _SQL_BASE
    params: list = []
    if excluidos:
        marcadores = ",".join("?" for _ in excluidos)
        sql += f"  AND e.id_empresa NOT IN ({marcadores})\n"
        params.extend(excluidos)
    sql += _ORDEN
    params.append(limite)

    con = sqlite3.connect(f"file:{ruta_prod}?mode=ro", uri=True)
    try:
        filas = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [
        EmpresaObjetivo(id_empresa=f[0], nombre_oficial=f[1], nombre_legal=f[2], usuarios=f[3])
        for f in filas
    ]


def cargar_por_nit(ruta_prod: str, nits: list[str]) -> list[EmpresaObjetivo]:
    marcadores = ",".join("?" for _ in nits)
    sql = (
        "SELECT id_empresa, nombre_oficial, COALESCE(nombre_legal, nombre_oficial), NULL "
        f"FROM empresa WHERE id_empresa IN ({marcadores})"
    )
    con = sqlite3.connect(f"file:{ruta_prod}?mode=ro", uri=True)
    try:
        filas = {f[0]: f for f in con.execute(sql, nits).fetchall()}
    finally:
        con.close()
    # respeta el orden pedido
    return [
        EmpresaObjetivo(
            id_empresa=filas[n][0], nombre_oficial=filas[n][1], nombre_legal=filas[n][2]
        )
        for n in nits
        if n in filas
    ]
