#!/bin/sh
set -e

echo "[entrypoint] Waiting for postgres..."
until python -c "
import sys, time, psycopg2, os
from app.core.config import get_settings
s = get_settings()
try:
    psycopg2.connect(s.DATABASE_URL.replace('postgresql+psycopg2', 'postgresql'))
except Exception as e:
    print(e)
    sys.exit(1)
"; do
  sleep 1
done

echo "[entrypoint] Running migrations..."
alembic upgrade head

echo "[entrypoint] Checking explicit demo seed configuration..."
python -m app.seed.bootstrap

echo "[entrypoint] Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
