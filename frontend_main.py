"""Convenience entry point for the evaluation frontend (development only).

The recommended way to run the frontend is uvicorn itself, from the project
root::

    uvicorn src.app.main:app --reload --port 8080

The Docker image runs the same command without ``--reload`` and with
``--host 0.0.0.0``. ``python frontend_main.py`` is only a shortcut (e.g. for
an IDE "Run" button).
"""

from src.app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.app.main:app", host="127.0.0.1", port=8080, reload=True)
