#!/bin/sh
set -e

python <<'PY'
import os
import time

import psycopg2
import redis

db_config = {
    "dbname": os.environ.get("DB_NAME", "shop_db"),
    "user": os.environ.get("DB_USER", "shop_user"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": os.environ.get("DB_PORT", "5432"),
}
redis_url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

for attempt in range(60):
    try:
        psycopg2.connect(**db_config).close()
        redis.Redis.from_url(redis_url).ping()
        break
    except Exception as exc:
        if attempt == 59:
            raise
        print(f"Waiting for dependencies: {exc}", flush=True)
        time.sleep(2)
PY

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    python manage.py migrate --noinput
fi

if [ "${RUN_COLLECTSTATIC:-1}" = "1" ]; then
    python manage.py collectstatic --noinput
fi

exec "$@"
