import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings  # noqa: E402
from src.flujos import directorio, scribd  # noqa: E402

NOMBRE = "METROTEL SA ESP"
NIT = "800204278"
ULTIMOS4 = ["6022"]

print(f"=== DIRECTORIOS para {NOMBRE} (NIT {NIT}), proxy={settings.camoufox_proxy!r} ===\n")

for fuente, funcion in [
    ("informacolombia", directorio.buscar_empresa_informacolombia),
    ("portafolio", directorio.buscar_empresa_portafolio),
    ("einforma", directorio.buscar_empresa_einforma),
]:
    print(f"--- {fuente} ---")
    try:
        res = funcion(NOMBRE, NIT, headless=True)
        print(res)
    except Exception as e:
        print(f"ERROR: {e!r}")
    print()

print(f"=== SCRIBD para {NOMBRE}, buscador={scribd._BUSCADOR!r} ===\n")
try:
    r = scribd.buscar_telefono_scribd(NOMBRE, ULTIMOS4, headless=True)
    print("documentos_revisados:", r["documentos_revisados"])
    print("match:", r["coincidencias"])
    print("candidatos:", r["posibles"][:5])
    print("razon:", r.get("razon"))
except Exception as e:
    print(f"ERROR: {e!r}")
