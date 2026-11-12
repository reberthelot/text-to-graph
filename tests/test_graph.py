"""Step 3 -- JSON-LD construction (``src/text2graph/graph.py``).

Driven by a fake linker (``tests.fakes.table_linker``): independent of
``linking.py``. The assignment examples are scored with the teacher's RDF
comparison, so "F1 = 1" means *the same triples*, whatever the local ids.

    uv run pytest tests/test_graph.py -q -m "not bonus"
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from src.app.utils.scoring import parse_graph, score_graphs
from src.text2graph.graph import build_jsonld
from src.text2graph.schema import Extraction, KeyboardModelFacts, OfferFacts
from src.text2graph.vocabulary import XSD_DATE, EntityKind, jsonld_context
from tests.examples import (
    EXAMPLE1_EXTRACTION,
    EXAMPLE1_JSONLD,
    EXAMPLE2_EXTRACTION,
    EXAMPLE2_JSONLD,
)
from tests.fakes import table_linker

BASE = "https://example.org/keyboards/extraction/00000000-0000-4000-8000-000000000000/"
LINKS = table_linker(
    {
        (EntityKind.MANUFACTURER, "Yamaha"): "kb:Q2",
        (EntityKind.MANUFACTURER, "Nord"): "kb:Q5",
        (EntityKind.COLOUR, "red"): "kb:Q104",
        (EntityKind.SELLER, "Morsø Musikhus"): "kb:Q70",
        (EntityKind.KEYBOARD_MODEL, "Nord Stage 4 88"): "kb:Q23",
        (EntityKind.KEYBOARD_MODEL, "Nord Stage 4 73"): "kb:Q24",
    }
)


def build(extraction: Extraction) -> dict[str, Any]:
    document = build_jsonld(extraction, LINKS, BASE)
    parse_graph(document)  # valid JSON-LD for the teacher's scorer
    return document


def node(document: dict[str, Any], node_id: str) -> dict[str, Any]:
    matches = [n for n in document["@graph"] if n["@id"] == node_id]
    assert len(matches) == 1, f"expected one node {node_id!r}, got {document['@graph']}"
    return matches[0]


# --- document shape --------------------------------------------------------------------


def test_empty_extraction_gives_an_empty_graph() -> None:
    assert build(Extraction()) == {"@context": jsonld_context(BASE), "@graph": []}


def test_context_carries_the_base() -> None:
    document = build(EXAMPLE2_EXTRACTION)
    assert document["@context"] == jsonld_context(BASE)


# --- the assignment examples ------------------------------------------------------------


@pytest.mark.parametrize(
    ("extraction", "reference"),
    [(EXAMPLE1_EXTRACTION, EXAMPLE1_JSONLD), (EXAMPLE2_EXTRACTION, EXAMPLE2_JSONLD)],
    ids=["example1-offer", "example2-two-models"],
)
def test_assignment_examples(extraction: Extraction, reference: dict[str, Any]) -> None:
    score = score_graphs(build(extraction), reference)
    assert score["exact"]
    assert (score["fp"], score["fn"]) == (0, 0), (
        f"extra: {score['extra']}\nmissing: {score['missing']}"
    )


# --- models -------------------------------------------------------------------------------


def test_unmatched_models_get_unique_local_ids_and_labels() -> None:
    names = ["PSR-E483", "Roland Jupiter-08", "Korg Triton"]
    document = build(Extraction(models=[KeyboardModelFacts(name=n, keys=61) for n in names]))
    ids = [n["@id"] for n in document["@graph"]]
    assert len(set(ids)) == 3
    assert all(not i.startswith(("kb:", "http")) for i in ids)  # relative to @base
    labels = {n["rdfs:label"]["@value"] for n in document["@graph"]}
    assert labels == set(names)
    assert all(n["rdfs:label"]["@language"] == "en" for n in document["@graph"])
    assert all(n["kbt:P11"] == {"@id": "kb:Q14"} for n in document["@graph"])


def test_linked_model_reuses_the_wikibase_id() -> None:
    document = build(
        Extraction(models=[KeyboardModelFacts(name="Nord Stage 4 88", keys=88, colour="red")])
    )
    model = node(document, "kb:Q23")
    assert "rdfs:label" not in model  # the catalogue already names it
    assert model["kbt:P11"] == {"@id": "kb:Q14"}
    assert model["kbt:P1"] == 88 and model["kbt:P9"] == {"@id": "kb:Q104"}


def test_zero_is_a_fact_but_none_is_not() -> None:
    model = build(Extraction(models=[KeyboardModelFacts(name="Nord Stage 4 73", loudspeakers=0)]))
    facts = node(model, "kb:Q24")
    assert facts["kbt:P10"] == 0  # "lack loudspeakers": stated, keep it
    assert "kbt:P1" not in facts and "kbt:P7" not in facts  # not stated: omit


def test_unlinked_manufacturer_and_colour_are_omitted() -> None:
    document = build(
        Extraction(models=[KeyboardModelFacts(name="X-1", manufacturer="Behringer", colour="teal")])
    )
    model = document["@graph"][0]
    assert "kbt:P6" not in model and "kbt:P9" not in model


# --- offers -------------------------------------------------------------------------------


def test_offer_with_seller_url_and_date() -> None:
    url = "http://momuhu.dk/index.php?route=product/product&path=59&product_id=1344"
    document = build(
        Extraction(
            models=[KeyboardModelFacts(name="Nord Stage 4 88")],
            offers=[
                OfferFacts(
                    model="Nord Stage 4 88",
                    seller="Morsø Musikhus",
                    price_dkk=4595,
                    url=url,
                    date=dt.date(2026, 10, 18),
                )
            ],
        )
    )
    assert len(document["@graph"]) == 1  # linked model without facts: no node
    offer = document["@graph"][0]
    assert offer["kbt:P11"] == {"@id": "kb:Q42"}
    assert offer["kbt:P24"] == {"@id": "kb:Q23"}
    assert offer["kbt:P23"] == {"@id": "kb:Q70"}
    assert offer["kbt:P25"] == 4595
    assert offer["kbt:P5"] == {"@id": url}  # an IRI, not a string literal
    assert offer["kbt:P26"] == {"@value": "2026-10-18", "@type": XSD_DATE}


def test_offer_for_an_unknown_model_points_to_a_local_node() -> None:
    document = build(
        Extraction(offers=[OfferFacts(model="Roland Jupiter-08", seller="Thomann", price_dkk=2500)])
    )
    assert len(document["@graph"]) == 2
    offer = next(n for n in document["@graph"] if n["kbt:P11"] == {"@id": "kb:Q42"})
    model = next(n for n in document["@graph"] if n["kbt:P11"] == {"@id": "kb:Q14"})
    assert offer["kbt:P24"] == {"@id": model["@id"]}
    assert model["rdfs:label"]["@value"] == "Roland Jupiter-08"
    assert "kbt:P23" not in offer  # unknown seller: omitted


def test_offers_get_unique_ids() -> None:
    offers = [OfferFacts(model="Nord Stage 4 88", price_dkk=p) for p in (20000, 21000)]
    document = build(Extraction(models=[KeyboardModelFacts(name="Nord Stage 4 88")], offers=offers))
    ids = [n["@id"] for n in document["@graph"]]
    assert len(ids) == len(set(ids)) == 2


# --- bonus ------------------------------------------------------------------------------


@pytest.mark.bonus
def test_bonus_two_mentions_of_one_catalogue_model_make_one_node() -> None:
    document = build(
        Extraction(
            models=[
                KeyboardModelFacts(name="Nord Stage 4 88", keys=88),
                KeyboardModelFacts(name="Nord Stage 4 88", colour="red"),
            ]
        )
    )
    model = node(document, "kb:Q23")  # exactly one node with this @id
    assert model["kbt:P1"] == 88 and model["kbt:P9"] == {"@id": "kb:Q104"}
