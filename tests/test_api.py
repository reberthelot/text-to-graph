"""HTTP layer of the text2graph service: contract and error mapping.

The pipeline is replaced by a stub, so these tests pass whatever the state
of your implementation (they test the plumbing, not your code).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.text2graph.errors import ExtractionError
from src.text2graph.llm import LLMNotConfiguredError, LLMTimeoutError, LLMUnavailableError
from src.text2graph.vocabulary import empty_document, new_base_iri

TEXT = {"text": "Der er kun 32 tangenter på et Roland SH-101."}


class StubPipeline:
    """Returns a fixed document, or raises ``error``."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def run(self, text: str) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        document = empty_document(new_base_iri())
        document["@graph"].append({"@id": "kb:Q18", "kbt:P1": 32})
        return document


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_extract_returns_a_jsonld_object(client: TestClient) -> None:
    client.app.state.pipeline = StubPipeline()
    response = client.post("/v1/extract", json=TEXT)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/ld+json")
    data = response.json()
    assert isinstance(data, dict)  # an object, not a string containing JSON
    assert set(data) == {"@context", "@graph"}
    assert data["@graph"] == [{"@id": "kb:Q18", "kbt:P1": 32}]


@pytest.mark.parametrize("body", [{}, {"text": ""}, {"question": "x"}])
def test_extract_rejects_invalid_body(client: TestClient, body: dict) -> None:
    assert client.post("/v1/extract", json=body).status_code == 422


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (NotImplementedError("graph.build_jsonld"), 501),
        (ExtractionError("no JSON object"), 502),
        (LLMNotConfiguredError("no key"), 503),
        (LLMTimeoutError("slow"), 504),
        (LLMUnavailableError("down"), 502),
        (RuntimeError("secret internals"), 500),
    ],
)
def test_error_mapping(client: TestClient, error: Exception, status: int) -> None:
    client.app.state.pipeline = StubPipeline(error)
    response = client.post("/v1/extract", json=TEXT)
    assert response.status_code == status
    assert "secret internals" not in response.text  # sanitized 500


def test_not_implemented_names_the_missing_step(client: TestClient) -> None:
    client.app.state.pipeline = StubPipeline(NotImplementedError("graph.build_jsonld"))
    assert "graph.build_jsonld" in client.post("/v1/extract", json=TEXT).json()["detail"]
