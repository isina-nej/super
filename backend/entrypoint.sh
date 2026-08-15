#!/bin/bash
set -euo pipefail

echo "Waiting for MySQL..."
python <<'PY'
import os, time, sys
import pymysql

host = os.getenv("MYSQL_HOST", "mysql")
port = int(os.getenv("MYSQL_PORT", "3306"))
user = os.getenv("MYSQL_USER", "bot")
password = os.getenv("MYSQL_PASSWORD", "botpass")
database = os.getenv("MYSQL_DATABASE", "download_bot")

for i in range(60):
    try:
        conn = pymysql.connect(
            host=host, port=port, user=user, password=password, database=database
        )
        conn.close()
        print("MySQL is ready.")
        sys.exit(0)
    except Exception as e:
        print(f"MySQL not ready ({e}); retry {i+1}/60")
        time.sleep(2)
print("MySQL wait timed out", file=sys.stderr)
sys.exit(1)
PY

echo "Running migrations..."
python manage.py migrate --noinput

if [ "${RUN_COLLECTSTATIC:-0}" = "1" ]; then
  python manage.py collectstatic --noinput || true
fi

exec "$@"
