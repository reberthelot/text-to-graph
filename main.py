"""Convenience entry point for the text2graph service (development only).

The recommended way to run the service is uvicorn itself, from the project
root (``.env`` is resolved relative to the working directory)::

    uvicorn src.text2graph.server:app --reload --port 8000

The Docker image runs the same command without ``--reload`` and with
``--host 0.0.0.0``. This module only adds ``python main.py`` (e.g. an IDE
"Run" button) and the ``main:app`` import path.
"""

from src.text2graph.server import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.text2graph.server:app", host="127.0.0.1", port=8000, reload=True)
