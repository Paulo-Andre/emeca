#!/bin/sh
set -eu

if [ "${SKIP_DJANGO_INIT:-0}" != "1" ]; then
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput
fi

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

exec gunicorn App.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --access-logfile - \
  --error-logfile -
