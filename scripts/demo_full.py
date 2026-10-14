"""Demo del pipeline completo (rues -> dian -> directorios -> scribd) sobre
UNA empresa, con progreso paso a paso y tabla final. Pensado para correr
visible (headless=False) para verlo en pantalla.
Uso: python scripts/demo_full.py <nit> [cedula_representante]
Si no se pasa cedula, se usa la del representante principal que traiga RUES.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from config.settings import settings  # noqa: E402
from src.engine import cargar_receta  # noqa: E402
from src.ejecutores.camoufox import CamoufoxEjecutor  # noqa: E402
from src.flujos import directorio, scribd  # noqa: E402
from src.rues import telefono  # noqa: E402

logger.remove()
logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | {message}", level="INFO")

VISIBLE = True  # headless=False: abre navegador real en pantalla

nit = sys.argv[1] if len(sys.argv) > 1 else "901358482"
cedula_forzada = sys.argv[2] if len(sys.argv) > 2 else None

resultado_final = {"nit": nit, "rues": [], "dian": None, "directorios": [], "scribd": None}

# ---------- 1. RUES ----------
print(f"\n=== ETAPA 1/4: RUES (representante legal + suplente) — NIT {nit} ===\n")
receta = cargar_receta(str(settings.dir_recetas / "rues_representante_legal.yaml"))
receta.headless = not VISIBLE
r_rues = CamoufoxEjecutor().ejecutar(receta, {"nit": nit})

nombre_empresa = None
cedula_principal = cedula_forzada
if r_rues.exito:
    representantes = r_rues.datos.get("representantes")
    contactos = representantes.get("contactos", []) if isinstance(representantes, dict) else []
    resultado_final["rues"] = contactos
    for c in contactos:
        print(f"  -> {c.get('nombre')} {c.get('apellido')} | {c.get('cargo')} | CC {c.get('documento')}")
        if c.get("es_rep_legal") and not cedula_principal:
            cedula_principal = c.get("documento")
else:
    print(f"  RUES fallo: {r_rues.error[:300]}")

if not cedula_principal:
    print("\nNo hay cedula de representante principal (RUES no la trajo). Deteniendo demo.")
    sys.exit(1)

# ---------- 2. DIAN ----------
print(f"\n=== ETAPA 2/4: DIAN (ultimos 4 del celular) — CC {cedula_principal} ===\n")
t_dian = telefono.buscar_dian(cedula_principal, headless=not VISIBLE)
resultado_final["dian"] = t_dian.numero
if t_dian.numero:
    print(f"  -> ultimos 4: {t_dian.numero}")
else:
    print("  -> sin dato en la DIAN para esta cedula")

# ---------- 3. Directorios ----------
print(f"\n=== ETAPA 3/4: Directorios (informacolombia, portafolio, einforma) ===\n")
if not nombre_empresa:
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{settings.prod_db_path}?mode=ro", uri=True)
        fila = con.execute(
            "SELECT nombre_legal, nombre_oficial FROM empresa WHERE id_empresa=?", (nit,)
        ).fetchone()
        nombre_empresa = (fila[0] or fila[1]) if fila else nit
    except Exception:
        nombre_empresa = nit

ultimos4 = [t_dian.numero] if t_dian.numero else []
confirmado = None
for fuente_nombre, funcion in [
    ("informacolombia", directorio.buscar_empresa_informacolombia),
    ("portafolio", directorio.buscar_empresa_portafolio),
    ("einforma", directorio.buscar_empresa_einforma),
]:
    try:
        res = funcion(nombre_empresa, nit, headless=not VISIBLE)
    except Exception as e:
        print(f"  {fuente_nombre}: ERROR -> {e!r}")
        continue
    if res.get("encontrado") and res.get("telefono"):
        numero = res["telefono"]
        match = any(numero.endswith(u) for u in ultimos4)
        resultado_final["directorios"].append({"fuente": fuente_nombre, "numero": numero, "match_dian": match})
        print(f"  {fuente_nombre}: {numero} {'(coincide con DIAN)' if match else ''}")
        if match:
            confirmado = numero
    else:
        print(f"  {fuente_nombre}: sin match ({res.get('razon', 'sin resultado')})")

# ---------- 4. Scribd (solo si no hay confirmado) ----------
print(f"\n=== ETAPA 4/4: Scribd (respaldo) ===\n")
if confirmado:
    print("  Ya hay numero confirmado por directorios, se salta Scribd.")
else:
    nombre_rep = None
    for c in resultado_final["rues"]:
        if c.get("es_rep_legal"):
            nombre_rep = f"{c.get('nombre')} {c.get('apellido')}"
    if nombre_rep and ultimos4:
        s = scribd.buscar_telefono_scribd(nombre_rep, ultimos4, headless=not VISIBLE)
        resultado_final["scribd"] = s
        print(f"  documentos revisados: {s['documentos_revisados']} de {s['docs_encontrados_total']} encontrados")
        if s.get("coincidencias"):
            confirmado = s["coincidencias"][0]["numero"]
            print(f"  -> CONFIRMADO via scribd: {confirmado}")
        else:
            print("  -> sin match en scribd")
    else:
        print("  sin nombre de representante o sin ultimos4, se salta")

# ---------- Tabla final ----------
print("\n" + "=" * 70)
print(f"RESUMEN FINAL — NIT {nit} ({nombre_empresa})")
print("=" * 70)
anchos = [22, 30, 12]
linea = "+" + "+".join("-" * (a + 2) for a in anchos) + "+"
print(linea)
print("|" + "|".join(f" {h:<{a}} " for h, a in zip(["ETAPA", "DATO", "ESTADO"], anchos)) + "|")
print(linea)
rep_ppal = next((c for c in resultado_final["rues"] if c.get("es_rep_legal")), None)
rep_supl = next((c for c in resultado_final["rues"] if not c.get("es_rep_legal")), None)
filas = [
    ("RUES principal", f"{rep_ppal.get('nombre')} {rep_ppal.get('apellido')}" if rep_ppal else "-", "OK" if rep_ppal else "SIN DATO"),
    ("RUES suplente", f"{rep_supl.get('nombre')} {rep_supl.get('apellido')}" if rep_supl else "-", "OK" if rep_supl else "SIN DATO"),
    ("DIAN (ult. 4)", resultado_final["dian"] or "-", "OK" if resultado_final["dian"] else "SIN DATO"),
    ("Telefono final", confirmado or "-", "CONFIRMADO" if confirmado else "SIN CONFIRMAR"),
]
for a, b, c_ in filas:
    print("|" + "|".join(f" {v:<{a2}} " for v, a2 in zip([a, b, c_], anchos)) + "|")
print(linea)
