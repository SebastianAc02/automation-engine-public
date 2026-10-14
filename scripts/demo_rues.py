"""Demo de la receta rues_representante_legal: muestra el progreso paso a
paso (via el logger del engine) y al final una tabla organizada con lo
que se extrajo.
Uso: python scripts/demo_rues.py <nit>"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from config.settings import settings  # noqa: E402
from src.engine import cargar_receta  # noqa: E402
from src.ejecutores.camoufox import CamoufoxEjecutor  # noqa: E402

logger.remove()
logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | {message}", level="INFO")

nit = sys.argv[1] if len(sys.argv) > 1 else "901320436"

print(f"\n=== Corriendo receta rues_representante_legal para NIT {nit} ===\n")

receta = cargar_receta(str(settings.dir_recetas / "rues_representante_legal.yaml"))
resultado = CamoufoxEjecutor().ejecutar(receta, {"nit": nit})

print()
if not resultado.exito:
    print("RESULTADO: fallo")
    print(resultado.error)
    sys.exit(1)

representantes = resultado.datos.get("representantes")
contactos = representantes.get("contactos", []) if isinstance(representantes, dict) else []

if not contactos:
    print("RESULTADO: sin representantes encontrados (pagina sin info)")
    crudo = resultado.datos.get("representantes_crudo")
    if crudo:
        print("--- respuesta cruda del modelo (no se pudo parsear como JSON) ---")
        print(crudo)
    sys.exit(0)

anchos = [24, 18, 40, 14, 12]
encabezado = ["NOMBRE", "APELLIDO", "CARGO", "DOCUMENTO", "PRINCIPAL"]
linea = "+" + "+".join("-" * (a + 2) for a in anchos) + "+"

print(linea)
print("|" + "|".join(f" {h:<{a}} " for h, a in zip(encabezado, anchos)) + "|")
print(linea)
for c in contactos:
    fila = [
        (c.get("nombre") or "")[:24],
        (c.get("apellido") or "")[:18],
        (c.get("cargo") or "")[:40],
        (c.get("documento") or "")[:14],
        "SI" if c.get("es_rep_legal") else "NO",
    ]
    print("|" + "|".join(f" {v:<{a}} " for v, a in zip(fila, anchos)) + "|")
print(linea)
