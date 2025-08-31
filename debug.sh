#!/bin/bash
source /home/pi/plant_dashboard/.venv/bin/activate
gunicorn --workers=2 --threads=4 --bind 0.0.0.0:8000 wsgi:app