"""Arma la lista priorizada de objetivos y la parte en N slices round-robin,
una por worker paralelo. Uso: python scripts/plan.py <N> <dir_salida>"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings  # noqa: E402
from src.rues.objetivos import seleccionar_batch  # noqa: E402

n = int(sys.argv[1])
salida = Path(sys.argv[2])
salida.mkdir(parents=True, exist_ok=True)

objetivos = seleccionar_batch(settings.prod_db_path, 100000)
for i in range(n):
    nits = [o.id_empresa for j, o in enumerate(objetivos) if j % n == i]
    (salida / f"slice_{i}.txt").write_text("\n".join(nits))
print(f"{len(objetivos)} objetivos priorizados en {n} slices en {salida}")
