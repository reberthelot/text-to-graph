"""Step 5 -- the whole service: POST /v1/extract with a scripted LLM.

Uses your three steps together (prompt + real linking + graph); green once
``test_prompts``, ``test_linking`` and ``test_graph`` are.

    uv run pytest tests/test_pipeline.py -q
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from src.app.utils.scoring import score_graphs
from src.text2graph.catalogue import Catalogue
from src.text2graph.pipeline import TextToGraph
from src.text2graph.vocabulary import EXTRACTION_ROOT
from tests.examples import (
    EXAMPLE1_EXTRACTION,
    EXAMPLE1_JSONLD,
    EXAMPLE1_TEXT,
    EXAMPLE2_EXTRACTION,
    EXAMPLE2_TEXT,
    example2_with_catalogue_link,
)
from tests.fakes import FakeLLM


def use_llm(client: TestClient, catalogue: Catalogue, *answers: str) -> FakeLLM:
    fake = FakeLLM(list(answers))
    client.app.state.pipeline = TextToGraph(fake, catalogue)
    return fake


def test_example2_end_to_end(client: TestClient, catalogue: Catalogue) -> None:
    fake = use_llm(client, catalogue, EXAMPLE2_EXTRACTION.model_dump_json())
    response = client.post("/v1/extract", json={"text": EXAMPLE2_TEXT})
    assert response.status_code == 200
    assert fake.response_formats[0] is not None  # structured outputs requested
    assert EXAMPLE2_TEXT in fake.calls[0][-1]["content"]
    score = score_graphs(response.json(), example2_with_catalogue_link())
    assert (score["fp"], score["fn"]) == (0, 0), f"{score['extra']}\n{score['missing']}"


def test_example1_end_to_end(client: TestClient, catalogue: Catalogue) -> None:
    use_llm(client, catalogue, EXAMPLE1_EXTRACTION.model_dump_json())
    response = client.post("/v1/extract", json={"text": EXAMPLE1_TEXT})
    assert score_graphs(response.json(), EXAMPLE1_JSONLD)["f1"] == 1.0


def test_every_extraction_has_its_own_uuid_base(client: TestClient, catalogue: Catalogue) -> None:
    use_llm(client, catalogue, EXAMPLE2_EXTRACTION.model_dump_json())
    bases = [
        client.post("/v1/extract", json={"text": EXAMPLE2_TEXT}).json()["@context"]["@base"]
        for _ in range(2)
    ]
    assert bases[0] != bases[1]
    for base in bases:
        assert base.startswith(EXTRACTION_ROOT) and base.endswith("/")
        uuid.UUID(base.removeprefix(EXTRACTION_ROOT).rstrip("/"))


def test_nothing_relevant_gives_an_empty_graph(client: TestClient, catalogue: Catalogue) -> None:
    use_llm(client, catalogue, '{"models": [], "offers": []}')
    response = client.post("/v1/extract", json={"text": "Yamaha XSR900 2027 weighs 193 kg"})
    assert response.status_code == 200 and response.json()["@graph"] == []


def test_unusable_llm_answer_is_a_502(client: TestClient, catalogue: Catalogue) -> None:
    use_llm(client, catalogue, "Sorry, I cannot help with that.")
    response = client.post("/v1/extract", json={"text": EXAMPLE1_TEXT})
    assert response.status_code == 502 and "Extraction failed" in response.json()["detail"]


@pytest.mark.live
def test_live_example1(client: TestClient, catalogue: Catalogue, live_llm) -> None:
    client.app.state.pipeline = TextToGraph(live_llm, catalogue)
    response = client.post("/v1/extract", json={"text": EXAMPLE1_TEXT})
    assert response.status_code == 200
    score = score_graphs(response.json(), EXAMPLE1_JSONLD)
    # Model facts are optional for ads: only the offer's triples are required.
    assert score["fn"] == 0, score["missing"]
