"""text2graph FastAPI application.

State (HTTP client, LLM client, catalogue, pipeline) is built **in the
lifespan**, never at import time: importing this module stays cheap and
side-effect free, which keeps the test suite fast (GUIDE section 6).

The service only *reads* a local snapshot of the Wikibase: it never modifies
the public Keyboards Wikibase.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .catalogue import Catalogue
from .config import get_settings
from .errors import ExtractionError
from .llm import LLMClient, LLMNotConfiguredError, LLMTimeoutError, LLMUnavailableError
from .models import ErrorResponse, ExtractRequest, HealthResponse
from .pipeline import TextToGraph

logger = logging.getLogger(__name__)

# The registered media type of JSON-LD (still plain JSON for any client).
JSONLD_MEDIA_TYPE = "application/ld+json"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load the catalogue, open the pooled HTTP client; release at shutdown."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not settings.campusai_api_key.get_secret_value():
        logger.warning("CAMPUSAI_API_KEY is missing: /v1/extract will return 503")

    # Fail fast: without its catalogue the service cannot link anything.
    catalogue = Catalogue.from_file(settings.catalogue_path)
    app.state.http_client = httpx.AsyncClient()
    app.state.pipeline = TextToGraph(LLMClient(settings, app.state.http_client), catalogue)
    logger.info("text2graph ready; %d catalogue entities, model %s", len(catalogue),
                settings.campusai_model)  # fmt: skip
    try:
        yield
    finally:
        await app.state.http_client.aclose()
        app.state.pipeline = None


def _error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


def create_app() -> FastAPI:
    """Application factory (used by tests and by ``main.py``)."""
    app = FastAPI(
        title="Keyboards text-to-graph",
        version="0.1.0",
        description="Extract keyboard models and offers from English / Danish text "
        "as JSON-LD, linked to the Keyboards Wikibase.",
        lifespan=lifespan,
    )

    # --- error mapping (GUIDE sections 4 and 7) ------------------------------
    # Our own messages (stubs, extraction) are safe to echo; upstream failures
    # get a generic message and the details go to the log.
    @app.exception_handler(NotImplementedError)
    async def _not_implemented(_: Request, exc: NotImplementedError) -> JSONResponse:
        return _error(501, f"Pipeline step not implemented yet: {exc}")

    @app.exception_handler(ExtractionError)
    async def _extraction(_: Request, exc: ExtractionError) -> JSONResponse:
        logger.warning("Extraction failed: %s", exc)
        return _error(502, f"Extraction failed: {exc}")

    @app.exception_handler(LLMNotConfiguredError)
    async def _llm_not_configured(_: Request, exc: LLMNotConfiguredError) -> JSONResponse:
        return _error(503, "The LLM is not configured (missing CAMPUSAI_API_KEY).")

    @app.exception_handler(LLMTimeoutError)
    async def _llm_timeout(_: Request, exc: LLMTimeoutError) -> JSONResponse:
        logger.exception("LLM call timed out")
        return _error(504, "Upstream LLM timed out.")

    @app.exception_handler(LLMUnavailableError)
    async def _llm_unavailable(_: Request, exc: LLMUnavailableError) -> JSONResponse:
        logger.exception("LLM unavailable")
        return _error(502, "Upstream LLM unavailable.")

    @app.exception_handler(Exception)
    async def _server_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s", request.url.path)
        return _error(500, "Internal server error")

    # --- endpoints -----------------------------------------------------------
    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    async def health() -> HealthResponse:
        """Liveness probe: constant, no dependencies, no side effects."""
        return HealthResponse()

    @app.post(
        "/v1/extract",
        response_class=JSONResponse,
        responses={
            200: {"description": "JSON-LD document", "content": {JSONLD_MEDIA_TYPE: {}}},
            **{code: {"model": ErrorResponse} for code in (422, 501, 502, 503, 504)},
        },
        tags=["text2graph"],
    )
    async def extract(request: Request, body: ExtractRequest) -> JSONResponse:
        """Extract the keyboard models and offers of ``text`` as JSON-LD."""
        pipeline: TextToGraph | None = getattr(request.app.state, "pipeline", None)
        if pipeline is None:
            return _error(503, "The service is still starting up.")
        document = await pipeline.run(body.text)
        return JSONResponse(document, media_type=JSONLD_MEDIA_TYPE)

    return app


# Module-level app for ``uvicorn src.text2graph.server:app``.
app = create_app()
