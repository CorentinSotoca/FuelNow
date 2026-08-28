#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="docker-compose.prod.yml"

echo "=== FuelNow deploy ==="

echo "[1/5] Git pull…"
git pull --ff-only

echo "[2/5] Build des images…"
docker compose -f "$COMPOSE_FILE" build

echo "[3/5] Démarrage de la DB…"
docker compose -f "$COMPOSE_FILE" up -d db
sleep 3

echo "[4/5] Migrations Alembic…"
docker compose -f "$COMPOSE_FILE" run --rm api alembic upgrade head

echo "[5/5] Démarrage des services…"
docker compose -f "$COMPOSE_FILE" up -d

echo "=== Déploiement terminé ==="
echo "Services :"
docker compose -f "$COMPOSE_FILE" ps
echo ""
echo "Health check :"
curl -sf http://localhost:${WEB_PORT:-8080}/health 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "(API pas encore prête, patientez quelques secondes)"
