#!/usr/bin/env sh
# Starts a fresh, seeded backend for e2e runs (demo mode on, no live network).
set -e
cd "$(dirname "$0")/../backend"
PY="${PYTHON:-../.venv/bin/python}"
DB="$(mktemp -d)/e2e.db"
export CM_DB_PATH="$DB" CM_DEV_MODE=true CM_JETSTREAM_ENABLED=false CM_EXPIRY_INTERVAL_S=2
"$PY" -m app.seed
exec "$PY" -m uvicorn app.main:app --port "${PORT:-8100}"
