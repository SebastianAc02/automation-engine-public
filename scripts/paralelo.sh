#!/bin/bash
# Lanza N workers en paralelo, cada uno con su perfil de Google y su base del
# engine. Cada worker procesa una slice de la lista priorizada. Reanudable:
# si se corta, al relanzar cada worker salta lo ya procesado.
# Uso: bash scripts/paralelo.sh [N] [dir_trabajo]
set -e
N="${1:-2}"
REPO="/Users/sebastianacostamolina/01_Documents/06_onepay/automation-engine"
DIR="${2:-$REPO/run}"
cd "$REPO"
mkdir -p "$DIR"

.venv/bin/python scripts/plan.py "$N" "$DIR"

for i in $(seq 0 $((N-1))); do
  # copia del perfil de Google por worker (evita el lock del perfil de Firefox)
  if [ ! -d "perfiles/google-$i" ]; then
    cp -R perfiles/google "perfiles/google-$i"
  fi
  RUES_PERFIL_GOOGLE="perfiles/google-$i" \
  ENGINE_DB_PATH="$DIR/rues_engine_$i.db" \
    caffeinate -is .venv/bin/python scripts/worker.py "$DIR/slice_$i.txt" \
    > "$DIR/worker_$i.log" 2>&1 &
  echo "worker $i lanzado (pid $!)"
  sleep 5
done
echo "N=$N workers corriendo. Logs en $DIR/worker_*.log"
wait
echo "=== todos los workers terminaron ==="
