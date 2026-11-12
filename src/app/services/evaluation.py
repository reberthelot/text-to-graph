"""Call the student service and score its JSON-LD (teacher's logic, unchanged).

Server-side requests avoid browser CORS and mixed-content restrictions. TLS
certificates remain verified, redirects are not followed, and extraction is
never retried implicitly (a retry would distort the timing).
"""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from ..models import ExtractRequest
from ..utils.scoring import parse_graph, score_graphs

MAX_RESPONSE_BYTES = 2_000_000


def validate_endpoint(endpoint: str) -> None:
    """Accept only a full http(s) URL without credentials, query or fragment."""
    url = urlsplit(endpoint)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError(
            "Use a full http(s) extraction URL without credentials, query or fragment."
        )
    _ = url.port  # raises ValueError on an invalid port


def _reject_constant(value: str) -> Any:
    raise ValueError(f"Non-finite JSON number: {value}")


async def extract_and_score(client: httpx.AsyncClient, payload: ExtractRequest) -> dict[str, Any]:
    """POST ``{"text": ...}`` to the student service, validate and score the answer.

    Returns
    -------
    dict
        ``prediction`` (raw JSON), ``elapsed_seconds``, and ``score`` when a
        reference is given, or ``validation_error`` when the JSON-LD is invalid
        (the raw prediction stays visible in the UI).
    """
    endpoint = payload.endpoint.strip()
    try:
        validate_endpoint(endpoint)
        if payload.reference is not None:
            await run_in_threadpool(parse_graph, payload.reference)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    start = perf_counter()
    try:
        async with client.stream(
            "POST", endpoint, json={"text": payload.text}, timeout=payload.timeout
        ) as response:
            if response.status_code != 200:
                raise HTTPException(502, f"Student service returned HTTP {response.status_code}.")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise HTTPException(502, "Student response exceeds 2 MB.")
        elapsed = perf_counter() - start
        prediction = json.loads(body, parse_constant=_reject_constant)
    except httpx.TimeoutException as error:
        raise HTTPException(
            504, f"Student service timed out after {payload.timeout:g} seconds."
        ) from error
    except httpx.RequestError as error:
        raise HTTPException(502, f"Could not reach student service: {error}") from error
    except (ValueError, UnicodeDecodeError) as error:
        raise HTTPException(502, "Student service did not return valid JSON.") from error
    result: dict[str, Any] = {"prediction": prediction, "elapsed_seconds": elapsed}
    try:
        await run_in_threadpool(parse_graph, prediction)
        if payload.reference is not None:
            result["score"] = await run_in_threadpool(score_graphs, prediction, payload.reference)
    except ValueError as error:
        # Keep the raw prediction visible even when its JSON-LD is invalid.
        result["validation_error"] = str(error)
    return result
