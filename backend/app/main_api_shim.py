"""Minimal FastAPI shim so make api (uv run uvicorn backend.app.main:app) works.

The FastAPI application lives in backend/app/main.py (create_app()).  This
shim is a placeholder keeping the make target resolvable: uvicorn import the
create_app callable without bootstrapping a MongoDB connection.
"""

from backend.app.main import create_app

app = create_app()
