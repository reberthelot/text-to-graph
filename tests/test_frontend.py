"""Evaluation frontend: pages, dataset, scoring and one extraction (mocked student)."""

from __future__ import annotations

import copy

import httpx
from fastapi.testclient import TestClient

from src.app.utils.scoring import score_graphs
from tests.examples import EXAMPLE2_JSONLD


def test_health_and_page(frontend_client: TestClient) -> None:
    assert frontend_client.get("/api/health").json() == {"status": "ok"}
    page = frontend_client.get("/")
    assert page.status_code == 200
    assert "Text-to-graph" in page.text
    assert frontend_client.get("/static/js/app.js").status_code == 200


def test_config_reflects_environment(frontend_client: TestClient) -> None:
    assert frontend_client.get("/api/config").json() == {
        "student_url": "http://student.test:8000/v1/extract"
    }


def test_server_dataset_loads(frontend_client: TestClient) -> None:
    data = frontend_client.get("/api/dataset").json()
    assert len(data["cases"]) == 10
    assert data["cases"][0]["name"] == "Yamaha GS1 weighs 90 kg"


def test_scoring_aligns_local_ids_and_numbers() -> None:
    renamed = copy.deepcopy(EXAMPLE2_JSONLD)
    renamed["@context"]["@base"] = "https://example.org/keyboards/extraction/other/"
    for node, new_id in zip(renamed["@graph"], ["a", "b"], strict=True):
        node["@id"] = new_id  # local ids differ...
    renamed["@graph"][0]["kbt:P7"] = 7  # ...and 7 == 7.0
    score = score_graphs(renamed, EXAMPLE2_JSONLD)
    assert score["f1"] == 1.0 and score["exact"]


def test_scoring_counts_a_wrong_link_twice() -> None:
    wrong = copy.deepcopy(EXAMPLE2_JSONLD)
    wrong["@graph"][0]["kbt:P6"] = {"@id": "kb:Q16"}  # Roland instead of Yamaha
    score = score_graphs(wrong, EXAMPLE2_JSONLD)
    assert (score["fp"], score["fn"]) == (1, 1)


def test_extract_end_to_end(frontend_client: TestClient) -> None:
    def student(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "student.test"
        return httpx.Response(200, json=EXAMPLE2_JSONLD)

    frontend_client.app.state.http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(student)
    )
    body = {
        "endpoint": "http://student.test:8000/v1/extract",
        "text": "Yamaha PSR-E483 and PSR-E583",
        "reference": EXAMPLE2_JSONLD,
    }
    data = frontend_client.post("/api/extract", json=body).json()
    assert data["score"]["f1"] == 1.0
    assert "validation_error" not in data


def test_extract_explains_unreachable_service(frontend_client: TestClient) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    frontend_client.app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    body = {"endpoint": "http://student.test:8000/v1/extract", "text": "x"}
    response = frontend_client.post("/api/extract", json=body)
    assert response.status_code == 502
    assert "Could not reach student service" in response.json()["detail"]
