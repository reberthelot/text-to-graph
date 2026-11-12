"""Provided building blocks: catalogue, schema, LLM-answer parsing, vocabulary.

These pass from the start: they document the tools your three steps use.
"""

from __future__ import annotations

import datetime as dt

import pytest

from src.text2graph.catalogue import Catalogue
from src.text2graph.errors import ExtractionError
from src.text2graph.extraction import parse_extraction
from src.text2graph.schema import EXTRACTION_RESPONSE_FORMAT, Extraction
from src.text2graph.vocabulary import EXTRACTION_ROOT, EntityKind, new_base_iri

# --- catalogue -------------------------------------------------------------------


def test_catalogue_snapshot(catalogue: Catalogue) -> None:
    kinds = {kind: len(catalogue.of_kind(kind)) for kind in EntityKind}
    assert kinds[EntityKind.MANUFACTURER] >= 10
    assert kinds[EntityKind.KEYBOARD_MODEL] >= 50
    assert kinds[EntityKind.COLOUR] >= 3
    assert kinds[EntityKind.SELLER] >= 3
    nord = catalogue.get("kb:Q5")
    assert nord is not None and nord.label == "Clavia DMI" and "Nord" in nord.aliases


def test_keyboards_without_p11_are_models(catalogue: Catalogue) -> None:
    organ = catalogue.get("kb:Q7")
    assert organ is not None and organ.kind == EntityKind.KEYBOARD_MODEL
    assert organ.label == "Nord Organ 3"


def test_danish_labels_are_aliases(catalogue: Catalogue) -> None:
    red = catalogue.get("kb:Q104")
    assert red is not None and red.label == "red" and "rød" in red.aliases


def test_prompt_listing_has_names_not_ids(catalogue: Catalogue) -> None:
    listing = catalogue.prompt_listing()
    assert "- Clavia DMI (also: Nord)" in listing
    assert "Nord Stage 4 88" in listing and "Morsø Musikhus" in listing
    assert "kb:Q" not in listing


# --- schema / structured outputs ------------------------------------------------------


def _object_schemas(node: object) -> list[dict]:
    if isinstance(node, dict):
        found = [node] if node.get("type") == "object" else []
        return found + [s for value in node.values() for s in _object_schemas(value)]
    if isinstance(node, list):
        return [s for item in node for s in _object_schemas(item)]
    return []


def test_response_format_is_strict() -> None:
    schema = EXTRACTION_RESPONSE_FORMAT["json_schema"]["schema"]
    assert EXTRACTION_RESPONSE_FORMAT["json_schema"]["strict"] is True
    objects = _object_schemas(schema)
    assert len(objects) == 3  # Extraction, KeyboardModelFacts, OfferFacts
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert sorted(obj["required"]) == sorted(obj["properties"])
    assert '"default"' not in str(schema).replace("'", '"')


# --- parse_extraction ---------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        '{"models": [{"name": "Roland SH-101", "keys": 32}], "offers": []}',
        'Sure!\n```json\n{"models": [{"name": "Roland SH-101", "keys": 32}]}\n```',
    ],
)
def test_parse_extraction_tolerates_wrapping_and_missing_keys(raw: str) -> None:
    extraction = parse_extraction(raw)
    assert extraction.models[0].name == "Roland SH-101"
    assert extraction.models[0].keys == 32
    assert extraction.models[0].weight_kg is None  # missing -> not stated
    assert extraction.offers == []


def test_parse_extraction_reads_dates_and_numbers() -> None:
    raw = '{"offers": [{"model": "Korg Pa700", "price_dkk": 9620, "date": "2025-09-19"}]}'
    offer = parse_extraction(raw).offers[0]
    assert offer.price_dkk == 9620 and offer.date == dt.date(2025, 9, 19)


@pytest.mark.parametrize(
    "raw",
    [
        "I could not find anything.",
        '{"models": [{"name": "x"',  # truncated
        '{"models": [{"keys": 61}]}',  # name is required
        '{"models": [], "colour": "red"}',  # unknown field
        '{"offers": [{"model": "x", "date": "18. oktober 2026"}]}',  # not ISO
    ],
)
def test_parse_extraction_rejects_unusable_answers(raw: str) -> None:
    with pytest.raises(ExtractionError):
        parse_extraction(raw)


def test_extraction_round_trip() -> None:
    extraction = Extraction.model_validate({"models": [{"name": "Korg M1", "loudspeakers": 0}]})
    assert parse_extraction(extraction.model_dump_json()) == extraction


# --- vocabulary ---------------------------------------------------------------------


def test_base_iri_is_a_fresh_uuid() -> None:
    import uuid

    base = new_base_iri()
    assert base.startswith(EXTRACTION_ROOT) and base.endswith("/")
    uuid.UUID(base.removeprefix(EXTRACTION_ROOT).rstrip("/"))
