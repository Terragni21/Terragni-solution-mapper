"""
WSGI entry point for Render (and any other WSGI host).

Gunicorn command:
    gunicorn wsgi:app
"""
from backend.app.app import app  # noqa: F401

if __name__ == "__main__":
    app.run()
