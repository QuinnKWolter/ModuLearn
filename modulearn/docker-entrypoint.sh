#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput
#python manage.py runserver 0.0.0.0:8000
# PCRS compilation/grading may take 30s; allow connection and local persistence
# to finish before Gunicorn terminates the worker. This is not a POST retry.
exec gunicorn modulearn.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60
