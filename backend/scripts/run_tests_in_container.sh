#!/usr/bin/env bash
# Ejecuta la suite (unit + integration, sin "slow") dentro de la imagen del backend
# contra el Postgres del proyecto compose, y guarda el resultado en JUnit XML.
#
# Uso: backend/scripts/run_tests_in_container.sh <dir_backend> <dir_salida> <nombre>
#   <dir_backend>  carpeta "backend" a montar en /app (p. ej. un worktree de un tag)
#   <dir_salida>   carpeta donde se escriben <nombre>.xml y <nombre>.log
#   <nombre>       prefijo de los ficheros de salida (p. ej. baseline_before)
#
# Requisitos: contenedor datamap-postgres en marcha y red dev-i18n-refactor_datamap-network.
# conftest.py fija REDIS_HOST=localhost y REDIS_PORT=6380, así que se levanta un Redis en
# 6380 y el contenedor de tests comparte su namespace de red (--network container:...).
set -u

BACKEND_DIR="$1"
OUT_DIR="$2"
NAME="$3"

NETWORK="${TEST_NETWORK:-dev-i18n-refactor_datamap-network}"
IMAGE="${TEST_IMAGE:-dev-i18n-refactor-backend:latest}"
REDIS_NAME="datamap-test-redis"

mkdir -p "$OUT_DIR"

# Redis de test (se reutiliza si ya existe)
if ! docker ps --format '{{.Names}}' | grep -qx "$REDIS_NAME"; then
  docker rm -f "$REDIS_NAME" >/dev/null 2>&1
  docker run -d --name "$REDIS_NAME" --network "$NETWORK" redis:7-alpine redis-server --port 6380 >/dev/null
  sleep 2
fi

# addopts se anula porque pytest.ini lleva --maxfail=5 y --ff (este último exige el plugin
# de caché, incompatible con -p no:cacheprovider). Se repiten los flags que sí interesan.
# ENV=development y SECRET_KEY replican docker-compose.yml: sin ellos app/config/security.py
# aborta la importación ("errores críticos de seguridad").
MSYS_NO_PATHCONV=1 docker run --rm --name datamap-test-runner \
  --network "container:$REDIS_NAME" \
  -v "$BACKEND_DIR:/app" -v "$OUT_DIR:/out" \
  -e TEST_DB_HOST=datamap-postgres -e TEST_DB_PORT=5432 \
  -e TEST_DB_USER=datamaper_user_local -e TEST_DB_PASSWORD=DataMap1234 \
  -e ENV=development -e SECRET_KEY='eWG%pN%xWGxY35_TwgWg_x23_2' \
  -e PYTHONDONTWRITEBYTECODE=1 \
  "$IMAGE" \
  python -m pytest -c pytest.ini --rootdir=. -o addopts="" \
    test/unit test/integration \
    -m "not slow" -p no:cacheprovider --maxfail=0 \
    --import-mode=importlib --tb=short -rfEs -q --durations=10 \
    --junitxml="/out/$NAME.xml" > "$OUT_DIR/$NAME.log" 2>&1
echo "exit=$?" >> "$OUT_DIR/$NAME.log"
