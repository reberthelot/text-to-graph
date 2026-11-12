"""Snapshot the linking catalogue from the live Keyboards Wikibase (read-only).

Writes ``data/catalogue.json``: every manufacturer, keyboard model, colour,
seller and country with its English label and its aliases (labels in other
languages + ``skos:altLabel``). The service links against this file, so the
test suite and the containers never need the network.

Keyboards without ``kbt:P11`` (e.g. Q7 Nord Organ 3) are still keyboard
models: they are included when they have a key count (``kbt:P1``).

Run from the project root, whenever the Wikibase gains new items::

    uv run python -m scripts.fetch_catalogue
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import httpx

from src.text2graph.vocabulary import CLASS_IDS, KB, EntityKind

logger = logging.getLogger(__name__)

ENDPOINT = "https://keyboards.wikibase.cloud/query/sparql"
OUTPUT = Path(__file__).resolve().parents[1] / "data" / "catalogue.json"

CLASS_VALUES = " ".join(CLASS_IDS.values())
QUERY = f"""
PREFIX kb: <{KB}>
PREFIX kbt: <https://keyboards.wikibase.cloud/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?item ?class ?kind ?name ?manufacturer WHERE {{
  {{ ?item kbt:P11 ?class . VALUES ?class {{ {CLASS_VALUES} }} }}
  UNION
  {{ ?item kbt:P1 [] . FILTER NOT EXISTS {{ ?item kbt:P11 [] }} BIND(kb:Q14 AS ?class) }}
  {{ ?item rdfs:label ?name . BIND("label" AS ?kind) }}
  UNION
  {{ ?item skos:altLabel ?name . BIND("alias" AS ?kind) }}
  OPTIONAL {{ ?item kbt:P6 ?manufacturer }}
}}
"""


def short(uri: str) -> str:
    return "kb:" + uri.removeprefix(KB)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    response = httpx.get(
        ENDPOINT,
        params={"query": QUERY},
        headers={"Accept": "application/sparql-results+json", "User-Agent": "dtu-text2graph"},
        timeout=60,
    )
    response.raise_for_status()
    kind_of_class = {class_id: kind for kind, class_id in CLASS_IDS.items()}

    entities: dict[str, dict] = {}
    names: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for row in response.json()["results"]["bindings"]:
        item = short(row["item"]["value"])
        entity = entities.setdefault(
            item,
            {"id": item, "kind": kind_of_class[short(row["class"]["value"])].value},
        )
        if "manufacturer" in row:
            entity["manufacturer"] = short(row["manufacturer"]["value"])
        name = row["name"]
        names[item].append((row["kind"]["value"], name.get("xml:lang", ""), name["value"]))

    for item, entity in entities.items():
        english = [v for kind, lang, v in names[item] if kind == "label" and lang == "en"]
        entity["label"] = english[0] if english else sorted(names[item])[0][2]
        others = {v for _, _, v in names[item]} - {entity["label"]}
        entity["aliases"] = sorted(others)

    ordered = sorted(
        entities.values(), key=lambda e: (list(EntityKind).index(e["kind"]), int(e["id"][4:]))
    )
    payload = {
        "source": ENDPOINT,
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "entities": ordered,
    }
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Wrote %d entities to %s", len(ordered), OUTPUT)


if __name__ == "__main__":
    main()
