"""Pydantic models: the HTTP contract of the service.

The response body is a JSON-LD document (``{"@context": ..., "@graph": [...]}``)
built by ``graph.build_jsonld``; its keys start with ``@``, so it is returned
as a plain dict rather than through a Pydantic model.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExtractRequest(BaseModel):
    """POST /v1/extract"""

    text: str = Field(
        min_length=1,
        max_length=100_000,
        description="Text describing keyboard models or offers (English or Danish)",
        examples=["Der er kun 32 tangenter på et Roland SH-101."],
    )


class HealthResponse(BaseModel):
    """GET /health"""

    status: Literal["ok"] = "ok"


class ErrorResponse(BaseModel):
    """Sanitized error body: never contains internal exception text."""

    detail: str
