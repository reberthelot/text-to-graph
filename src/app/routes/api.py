"""JSON endpoints called by the browser: health, defaults, dataset, compare, extract.

Thin layer: each route validates its body (pydantic) and delegates to
``utils`` (pure scoring / dataset parsing) or ``services.evaluation`` (I/O).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from ..config import Settings
from ..models import (
    CompareRequest,
    ConfigResponse,
    DatasetRequest,
    DatasetResponse,
    ExtractRequest,
    HealthResponse,
)
from ..services.evaluation import extract_and_score
from ..utils.dataset import parse_dataset
from ..utils.scoring import parse_graph, score_graphs

router = APIRouter(prefix="/api")


def _validated_cases(content: str) -> list[dict[str, Any]]:
    """Parse a dataset and check that every reference is valid JSON-LD."""
    cases = parse_dataset(content)
    for case in cases:
        parse_graph(case["reference"])
    return cases


@router.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    """Liveness probe: constant, no dependencies, no side effects."""
    return HealthResponse()


@router.get("/config", response_model=ConfigResponse, tags=["ui"])
async def config(request: Request) -> ConfigResponse:
    """Default student endpoint shown in the UI (from ``STUDENT_URL``)."""
    settings: Settings = request.app.state.settings
    return ConfigResponse(student_url=settings.student_url)


@router.get("/dataset", response_model=DatasetResponse, tags=["dataset"])
async def initial_dataset(request: Request) -> DatasetResponse:
    """The server dataset (``data/keyboards.txt``)."""
    settings: Settings = request.app.state.settings
    try:
        content = settings.dataset_path.read_text(encoding="utf-8")
        cases = await run_in_threadpool(_validated_cases, content)
    except (ValueError, OSError) as error:
        raise HTTPException(400, str(error)) from error
    return DatasetResponse(cases=cases, source=settings.dataset_path.name)


@router.post("/dataset/parse", response_model=DatasetResponse, tags=["dataset"])
async def import_dataset(payload: DatasetRequest) -> DatasetResponse:
    """Parse an imported ``.txt`` dataset (the browser keeps the cases)."""
    try:
        cases = await run_in_threadpool(_validated_cases, payload.content)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return DatasetResponse(cases=cases, source="import")


@router.post("/compare", tags=["evaluation"])
async def compare(payload: CompareRequest) -> dict[str, Any]:
    """Score a pasted prediction against a reference, offline."""
    try:
        return await run_in_threadpool(score_graphs, payload.prediction, payload.reference)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.post("/extract", tags=["evaluation"])
async def extract(request: Request, payload: ExtractRequest) -> dict[str, Any]:
    """Call the student service and score its answer against the reference."""
    return await extract_and_score(request.app.state.http_client, payload)
