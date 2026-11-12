"""Frontend application factory and lifespan.

State (settings, pooled HTTP client) lives on ``app.state`` and is created in
the lifespan: importing this module stays cheap and side-effect free (GUIDE §6).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import REPO_ROOT, get_settings
from .routes import api, frontend

STATIC_DIR = REPO_ROOT / "frontend" / "static"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure logging, open the pooled client, release it on shutdown."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    app.state.settings = settings
    # No redirects, no proxy from the environment, no automatic retries.
    app.state.http_client = httpx.AsyncClient(follow_redirects=False, trust_env=False)
    logger.info("Frontend ready; default student service at %s", settings.student_url)
    try:
        yield
    finally:
        await app.state.http_client.aclose()


def create_app() -> FastAPI:
    """Build the frontend application."""
    app = FastAPI(
        title="Text-to-graph evaluation UI",
        version="0.1.0",
        description="Inspect keyboard extractions and compare RDF triples against "
        "editable reference graphs.",
        lifespan=lifespan,
    )
    app.include_router(api.router)
    app.include_router(frontend.router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app


# Module-level app for ``uvicorn src.app.main:app``.
app = create_app()
