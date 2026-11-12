"""Pydantic models of the frontend API (browser <-> frontend).

Field names are those of the original single-file frontend: the JavaScript
in ``frontend/static/js/app.js`` sends and reads exactly these keys.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ExtractRequest(BaseModel):
    """POST /api/extract: call the student service, then score its answer."""

    endpoint: str = Field(min_length=1, max_length=2048)
    text: str = Field(min_length=1, max_length=100_000)
    timeout: float = Field(default=60, ge=1, le=300)
    reference: dict[str, Any] | None = None


class CompareRequest(BaseModel):
    """POST /api/compare: score a pasted prediction offline."""

    prediction: dict[str, Any]
    reference: dict[str, Any]


class DatasetRequest(BaseModel):
    """POST /api/dataset/parse: content of an imported ``.txt`` dataset."""

    content: str = Field(max_length=5_000_000)


class DatasetResponse(BaseModel):
    """GET /api/dataset and POST /api/dataset/parse"""

    cases: list[dict[str, Any]]
    source: str = ""
    sample: bool = False


class ConfigResponse(BaseModel):
    """GET /api/config: defaults shown in the UI."""

    student_url: str


class HealthResponse(BaseModel):
    """GET /api/health"""

    status: Literal["ok"] = "ok"
