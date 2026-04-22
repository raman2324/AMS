#!/bin/sh
set -e

python << 'PYEOF'
import os, sys, time

db_url = os.environ.get('DATABASE_URL', '')
if db_url.startswith('postgres'):
    import psycopg2
    print("Waiting for PostgreSQL...")
    for i in range(30):
        try:
            conn = psycopg2.connect(db_url)
            conn.close()
            print("PostgreSQL is ready.")
            break
        except psycopg2.OperationalError:
            time.sleep(1)
    else:
        print("ERROR: PostgreSQL not available after 30 seconds", file=sys.stderr)
        sys.exit(1)
PYEOF

python manage.py migrate --noinput
python manage.py seed_data
python manage.py collectstatic --noinput --clear

exec "$@"
