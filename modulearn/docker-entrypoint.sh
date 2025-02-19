#!/bin/sh
python manage.py makemigrations admin accounts courses
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
