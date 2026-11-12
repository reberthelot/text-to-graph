"""Shared fixtures: lifespan-aware clients, the catalogue, the live LLM.

No network by default: the LLM is a scripted ``FakeLLM``, linking runs on the
committed snapshot ``data/catalogue.json``, and the frontend's upstream calls
go through an ``httpx.MockTransport``.

Exception: tests marked ``live`` use the ``live_llm`` fixture (the real
CampusAI LLM). They run by default and are skipped -- with the reason -- when
the endpoint does not answer (``-rs`` shows it) or with ``--no-live``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from src.app.main import create_app as create_frontend_app
from src.text2graph.catalogue import Catalogue
from src.text2graph.config import REPO_ROOT, get_settings
from src.text2graph.llm import LLMClient
from src.text2graph.server import create_app

CATALOGUE_PATH = REPO_ROOT / "data" / "catalogue.json"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--no-live", action="store_true", help="skip the tests calling the real CampusAI LLM"
    )


def _llm_unavailable_reason() -> str | None:
    """Probe CampusAI once (``GET {url}/models``): ``None`` if it answers, else why not."""
    settings = get_settings()
    api_key = settings.campusai_api_key.get_secret_value()
    if not api_key:
        return "CAMPUSAI_API_KEY is not set"
    url = settings.campusai_api_url.rstrip("/") + "/models"
    try:
        response = httpx.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=5.0)
    except httpx.HTTPError as exc:  # timeout, DNS, refused... (off the DTU network / VPN)
        return f"CampusAI unreachable ({type(exc).__name__})"
    if response.status_code >= 400:
        return f"CampusAI answered HTTP {response.status_code}"
    return None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Run ``live`` tests by default, skip them if the LLM endpoint does not answer.

    The endpoint is probed once, and only when live tests were collected, so
    the offline suite never touches the network.
    """
    live_items = [item for item in items if "live" in item.keywords]
    if not live_items:
        return
    reason = "--no-live" if config.getoption("--no-live") else _llm_unavailable_reason()
    if reason is None:
        return
    skip_live = pytest.mark.skip(reason=f"live LLM tests skipped: {reason}")
    for item in live_items:
        item.add_marker(skip_live)


class LiveLLM:
    """The real ``LLMClient``, with the same surface as ``FakeLLM``.

    One ``httpx.AsyncClient`` per call: the tests drive coroutines with
    ``asyncio.run``, and a pooled client cannot be shared across event loops.
    ``answers`` keeps every raw answer (shown with ``pytest -s``).
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self.answers: list[str] = []

    async def complete(
        self, messages: list[dict[str, str]], response_format: dict[str, Any] | None = None
    ) -> str:
        async with httpx.AsyncClient() as http:
            raw = await LLMClient(self._settings, http).complete(messages, response_format)
        self.answers.append(raw)
        print(f"\n[live LLM] -> {raw}")
        return raw


@pytest.fixture(scope="session")
def live_llm() -> LiveLLM:
    """Real CampusAI client, for tests marked ``live``.

    Session scope: built before any function fixture, so it reads the real
    ``CAMPUSAI_API_KEY`` before ``client`` replaces it with a dummy key.
    """
    return LiveLLM()


@pytest.fixture(scope="session")
def catalogue() -> Catalogue:
    """The committed Wikibase snapshot (76 entities)."""
    return Catalogue.from_file(CATALOGUE_PATH)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """``with`` triggers the lifespan. Tests replace ``app.state.pipeline``.

    ``raise_server_exceptions=False``: let the 500 handler answer, as a real
    client would see it, instead of re-raising inside the test.
    """
    monkeypatch.setenv("CAMPUSAI_API_KEY", "test-key")
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture()
def frontend_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Lifespan-aware client of the evaluation frontend."""
    monkeypatch.setenv("STUDENT_URL", "http://student.test:8000/v1/extract")
    with TestClient(create_frontend_app()) as test_client:
        yield test_client
