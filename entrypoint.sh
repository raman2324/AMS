#!/bin/sh
set -e

python << 'PYEOF'
import os, sys, time
from urllib.parse import urlparse

db_url = os.environ.get('DATABASE_URL', '')
if db_url.startswith('mysql'):
    import MySQLdb
    p = urlparse(db_url)
    print("Waiting for MySQL...")
    for i in range(30):
        try:
            conn = MySQLdb.connect(
                host=p.hostname,
                port=p.port or 3306,
                user=p.username,
                passwd=p.password,
                db=p.path.lstrip('/'),
            )
            conn.close()
            print("MySQL is ready.")
            break
        except MySQLdb.OperationalError:
            time.sleep(1)
    else:
        print("ERROR: MySQL not available after 30 seconds", file=sys.stderr)
        sys.exit(1)
PYEOF

python manage.py migrate --noinput
python manage.py seed_data
python manage.py collectstatic --noinput --clear

exec "$@"
