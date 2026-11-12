"""JSON-LD construction: linked extraction -> RDF graph.   <-- YOUR PART (step 3)

This is the *text-to-graph* step proper: turn the flat ``Extraction`` into
nodes and triples of the Keyboards vocabulary (``vocabulary.py``), e.g.

.. code-block:: json

    {"@context": {"@base": "https://example.org/keyboards/extraction/<uuid>/",
                  "kb": "...", "kbt": "...", "rdfs": "..."},
     "@graph": [
       {"@id": "model/1",
        "rdfs:label": {"@value": "PSR-E483", "@language": "en"},
        "kbt:P11": {"@id": "kb:Q14"}, "kbt:P6": {"@id": "kb:Q2"}, "kbt:P1": 61},
       {"@id": "offer/1", "kbt:P11": {"@id": "kb:Q42"},
        "kbt:P24": {"@id": "kb:Q23"}, "kbt:P25": 26500,
        "kbt:P5": {"@id": "https://..."},
        "kbt:P26": {"@value": "2026-10-18",
                    "@type": "http://www.w3.org/2001/XMLSchema#date"}}]}

Linking is *injected* (``link``) rather than imported: the tests drive this
module with a fake linker, so it can be developed independently of
``linking.py``.

Contract: ``tests/test_graph.py`` (scored with the teacher's RDF comparison).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .schema import Extraction, KeyboardModelFacts
from .vocabulary import (  # noqa: F401  (everything you need to name things)
    INSTANCE_OF,
    KEYBOARD_MODEL_CLASS,
    LABEL,
    MODEL_LINKS,
    MODEL_QUANTITIES,
    OFFER_CLASS,
    OFFER_DATE,
    OFFER_MODEL,
    OFFER_PRICE,
    OFFER_SELLER,
    OFFER_URL,
    XSD_DATE,
    EntityKind,
    jsonld_context,
)

# (surface string or None, kind) -> "kb:Q…" or None. See linking.link_entity.
Linker = Callable[[str | None, EntityKind], str | None]


def build_jsonld(extraction: Extraction, link: Linker, base: str) -> dict[str, Any]:
    """JSON-LD document of ``extraction``, with a shared ``@context`` and an ``@graph``.

    Parameters
    ----------
    extraction : Extraction
        Models and offers returned by the LLM (surface strings, target units).
    link : Linker
        Entity linker; ``None`` means "no confident match".
    base : str
        ``@base`` of this extraction (``EXTRACTION_ROOT + uuid + "/"``), made
        by the caller: local ids are relative to it (``"model/1"``).

    Returns
    -------
    dict
        ``{"@context": jsonld_context(base), "@graph": [...]}``; the graph is
        ``[]`` when nothing relevant was extracted.

    Rules (from the assignment)
    ---------------------------
    * linked model -> node ``"@id": "kb:Q…"``; unmatched model -> local node
      ``"model/<n>"`` with an ``rdfs:label``; local ids unique per extraction;
    * every emitted model node is typed ``kbt:P11 kb:Q14``; a linked model
      with no extracted fact needs no node (the catalogue already knows it);
    * offers -> ``"offer/<n>"``, typed ``kb:Q42``, linked to their model node;
    * omit unknown values (``None``) and unlinked manufacturers / colours /
      sellers -- but keep a stated ``0``.
    """
    nodes: dict[str, dict[str, Any]] = {}  # @id -> node (insertion-ordered)
    model_ids: dict[str, str] = {}  # model name as extracted -> @id of its node
    n_models = 0

    def local_model(name: str) -> str:
        """New local, labelled model node; returns its relative @id."""
        nonlocal n_models
        n_models += 1
        node_id = f"model/{n_models}"
        nodes[node_id] = {
            "@id": node_id,
            LABEL: {"@value": name, "@language": "en"},
            INSTANCE_OF: {"@id": KEYBOARD_MODEL_CLASS},
        }
        return node_id

    for model in extraction.models:
        facts = _model_facts(model, link)

        if model.name in model_ids:  # second mention of the same model: merge
            node_id = model_ids[model.name]
        elif qid := link(model.name, EntityKind.KEYBOARD_MODEL):
            node_id = qid
        else:
            node_id = local_model(model.name)
        model_ids[model.name] = node_id
        if node_id not in nodes:
            if not facts:  # linked and nothing new: the catalogue already knows it
                continue
            nodes[node_id] = {"@id": node_id, INSTANCE_OF: {"@id": KEYBOARD_MODEL_CLASS}}
        nodes[node_id].update(facts)

    for n_offers, offer in enumerate(extraction.offers, start=1):
        model_id = model_ids.get(offer.model) or link(offer.model, EntityKind.KEYBOARD_MODEL)

        if model_id is None:  # offer for a model absent from `models` and the catalogue
            model_id = local_model(offer.model)

        model_ids[offer.model] = model_id
        offer_id = f"offer/{n_offers}"
        node: dict[str, Any] = {
            "@id": offer_id,
            INSTANCE_OF: {"@id": OFFER_CLASS},
            OFFER_MODEL: {"@id": model_id},
        }
        if seller := link(offer.seller, EntityKind.SELLER):
            node[OFFER_SELLER] = {"@id": seller}
        if offer.price_dkk is not None:
            node[OFFER_PRICE] = _number(offer.price_dkk)
        if offer.url is not None:
            node[OFFER_URL] = {"@id": offer.url}  # an IRI, not a string literal
        if offer.date is not None:
            node[OFFER_DATE] = {"@value": offer.date.isoformat(), "@type": XSD_DATE}
        nodes[offer_id] = node

    return {"@context": jsonld_context(base), "@graph": list(nodes.values())}


def _number(value: float) -> int | float:
    """``992.0 -> 992`` for readability; the scorer compares by value anyway."""
    return int(value) if float(value).is_integer() else value


def _model_facts(model: KeyboardModelFacts, link: Linker) -> dict[str, Any]:
    """Predicate -> object of every *stated* fact (``0`` kept, ``None`` dropped)."""
    facts: dict[str, Any] = {
        prop: _number(value)
        for field, prop in MODEL_QUANTITIES.items()
        if (value := getattr(model, field)) is not None
    }
    for field, (prop, kind) in MODEL_LINKS.items():
        if qid := link(getattr(model, field), kind):  # unlinked -> omitted
            facts[prop] = {"@id": qid}
    return facts
