#!/bin/sh
set -e

echo "[entrypoint] Waiting for database..."
python -c "
import time
import sys
from sqlalchemy import create_engine, text
from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.DATABASE_URL)

for attempt in range(30):
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        print('[entrypoint] Database is ready.')
        sys.exit(0)
    except Exception as exc:
        print(f'[entrypoint] Database not ready yet ({attempt+1}/30): {exc}')
        time.sleep(2)
sys.exit(1)
"

echo "[entrypoint] Running Alembic migrations..."
alembic upgrade head

echo "[entrypoint] Starting application..."
exec "$@"
