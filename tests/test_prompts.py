"""Step 4 -- the extraction prompt (``src/text2graph/prompts.py``).

The structure is tested offline; the *quality* of the prompt only with the
real LLM (``live`` tests, skipped when CampusAI does not answer).

    uv run pytest tests/test_prompts.py -q --no-live     # structure
    uv run pytest tests/test_prompts.py -v -s -rs        # + live, shows raw answers
"""

from __future__ import annotations

import asyncio

import pytest

from src.app.utils.dataset import parse_dataset
from src.text2graph.catalogue import Catalogue
from src.text2graph.config import REPO_ROOT
from src.text2graph.extraction import extract_facts
from src.text2graph.prompts import build_extraction_messages
from src.text2graph.schema import Extraction
from tests.examples import EXAMPLE1_TEXT, EXAMPLE2_TEXT

TEXT = "Der er kun 32 tangenter på et Roland SH-101."


@pytest.fixture()
def messages(catalogue: Catalogue) -> list[dict[str, str]]:
    return build_extraction_messages(TEXT, catalogue)


def test_messages_shape(messages: list[dict[str, str]]) -> None:
    assert all(set(m) == {"role", "content"} for m in messages)
    assert all(isinstance(m["content"], str) and m["content"].strip() for m in messages)
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user" and TEXT in messages[-1]["content"]


def test_few_shot_turns_alternate(messages: list[dict[str, str]]) -> None:
    shots = messages[1:-1]
    assert len(shots) >= 4, "at least two few-shot (user, assistant) pairs"
    assert [m["role"] for m in shots] == ["user", "assistant"] * (len(shots) // 2)


def test_few_shot_answers_follow_the_schema(messages: list[dict[str, str]]) -> None:
    answers = [Extraction.model_validate_json(m["content"]) for m in messages[2:-1:2]]
    assert any(a.models for a in answers), "show at least one keyboard model"
    assert any(a.offers for a in answers), "show at least one offer"


def test_prompt_lists_the_catalogue(messages: list[dict[str, str]]) -> None:
    # Schema-aware prompting: the LLM must know the canonical names to copy
    # them ("Nord Stage 4 88" for "Nord Stage 4 med 88 tangenter").
    prompt = "\n".join(m["content"] for m in messages)
    assert "Nord Stage 4 88" in prompt and "Clavia DMI" in prompt


def test_few_shots_do_not_leak_test_texts(messages: list[dict[str, str]]) -> None:
    dataset = (REPO_ROOT / "data" / "keyboards.txt").read_text(encoding="utf-8")
    tests = [case["text"] for case in parse_dataset(dataset)] + [EXAMPLE1_TEXT, EXAMPLE2_TEXT]
    shots = [m["content"] for m in messages[1:-1:2]]
    for text in tests:
        opening = " ".join(text.split())[:50]
        assert not any(opening in " ".join(shot.split()) for shot in shots), opening


# --- live: the real LLM on the assignment examples ----------------------------------------


@pytest.mark.live
def test_live_example2_specifications(catalogue: Catalogue, live_llm) -> None:
    extraction = asyncio.run(extract_facts(EXAMPLE2_TEXT, live_llm, catalogue))
    assert len(extraction.models) == 2 and not extraction.offers
    e483, e583 = sorted(extraction.models, key=lambda m: m.name)
    for model in (e483, e583):
        assert model.keys == 61 and model.polyphony == 64
        assert model.width_mm == pytest.approx(992) and model.depth_mm == pytest.approx(404)
        assert model.height_mm == pytest.approx(136)  # not the 216 mm box
        assert model.power_consumption_w == pytest.approx(13)  # not the 6 W channels
        assert (model.headphone_outputs, model.audio_outputs) == (1, 2)
        assert (model.microphone_inputs, model.audio_inputs) == (1, 1)
    assert (e483.weight_kg, e583.weight_kg) == (pytest.approx(7.0), pytest.approx(7.3))


@pytest.mark.live
def test_live_example1_danish_offer(catalogue: Catalogue, live_llm) -> None:
    extraction = asyncio.run(extract_facts(EXAMPLE1_TEXT, live_llm, catalogue))
    assert len(extraction.offers) == 1
    offer = extraction.offers[0]
    assert offer.price_dkk == pytest.approx(26500)  # "26.500 kr." is not 26.5
    assert offer.date is not None and offer.date.isoformat() == "2026-10-18"
    assert offer.model == "Nord Stage 4 88"  # canonical catalogue name


@pytest.mark.live
def test_live_irrelevant_text_gives_nothing(catalogue: Catalogue, live_llm) -> None:
    text = "Yamaha XSR900 2027 has a motor on 890 cc and weighs 193 kg"
    assert asyncio.run(extract_facts(text, live_llm, catalogue)) == Extraction()
