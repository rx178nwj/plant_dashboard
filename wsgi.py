# wsgi.py
# This file is the entry point for the Gunicorn server.

import threading
from app import create_app, run_async_loop, init_db

# Initialize the database when the server starts.
init_db()

# Create the Flask app instance using the factory.
app = create_app()

# Start the background data collection thread.
# This is safe for a single-worker setup.
bg_thread = threading.Thread(target=run_async_loop, daemon=True)
bg_thread.start()
