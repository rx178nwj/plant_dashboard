#!/bin/bash
source /home/pi/plant_dashboard/.env
source /home/pi/plant_dashboard/.venv/bin/activate
gunicorn --workers=4 --threads=4 --bind 0.0.0.0:8000 --access-logfile logs/access.log --error-logfile logs/error.log wsgi:app
