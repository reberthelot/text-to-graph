"""RDF graph comparison: triple precision / recall / F1 (teacher's logic, unchanged).

Ported from ``text-to-graph-ui.py``; only type hints and comments were added.

How a prediction is scored against a reference JSON-LD document:

1. Both documents are **expanded to RDF triples** with rdflib (so
   ``"kbt:P1": 61`` and the full IRI form are the same triple).
2. **Local nodes** (IRIs under ``EXTRACTION_ROOT`` and blank nodes) become
   anonymous variables: ``model/1`` in the prediction may align with
   ``model/PSR-E483`` in the reference. Catalogue IRIs (``kb:Q23``) stay fixed,
   so a wrong link is a wrong triple.
3. A branch-and-bound search finds the **one-to-one alignment** of local nodes
   that maximizes the number of shared triples.
4. Numbers compare by value (``7 == 7.0``); every triple counts, labels and
   ``kbt:P11`` type statements included.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from time import monotonic
from typing import Any

from rdflib import XSD, BNode, Graph, Literal, URIRef

EXTRACTION_ROOT = "https://example.org/keyboards/extraction/"
FALLBACK_BASE = EXTRACTION_ROOT + "unbased/"
NUMERIC_TYPES = {
    XSD.integer, XSD.decimal, XSD.double, XSD.float, XSD.int, XSD.long,
    XSD.short, XSD.byte, XSD.nonNegativeInteger, XSD.positiveInteger,
    XSD.nonPositiveInteger, XSD.negativeInteger, XSD.unsignedInt,
    XSD.unsignedLong, XSD.unsignedShort, XSD.unsignedByte,
}  # fmt: skip

Triple = tuple[Any, Any, Any]


def check_contexts(value: Any, *, root: bool = True) -> None:
    """Reject remote contexts and nested graphs before invoking RDFLib."""
    if isinstance(value, list):
        for item in value:
            check_contexts(item, root=False)
    elif isinstance(value, dict):
        if "@import" in value:
            raise ValueError("JSON-LD @import is not supported; use an inline context.")
        if not root and "@graph" in value:
            raise ValueError("Nested/named graphs are not supported in this exercise.")
        for key, item in value.items():
            if key == "@context":
                contexts = item if isinstance(item, list) else [item]
                if any(c is not None and not isinstance(c, dict) for c in contexts):
                    raise ValueError("Use inline JSON-LD contexts; remote contexts are disabled.")
            check_contexts(item, root=False)


def _reject_aliases(value: Any) -> None:
    """Aliases for graph/context keywords could otherwise bypass the checks."""
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                not key.startswith("@")
                and isinstance(item, str)
                and item in {"@context", "@graph", "@import", "@included"}
            ):
                raise ValueError(f"Aliases for {item} are not supported.")
            _reject_aliases(item)
    elif isinstance(value, list):
        for item in value:
            _reject_aliases(item)


def _normalize(term: Any) -> Any:
    """Local nodes -> alignment variables; numbers -> canonical xsd:decimal."""
    if isinstance(term, URIRef) and str(term).startswith(EXTRACTION_ROOT):
        return BNode("uri:" + str(term))
    if isinstance(term, BNode):
        return BNode("blank:" + str(term))
    if isinstance(term, Literal) and term.datatype in NUMERIC_TYPES:
        try:
            number = Decimal(str(term))
            if not number.is_finite():
                raise ValueError("Non-finite numbers are not supported.")
            # format(..., 'f') avoids scientific notation in xsd:decimal.
            lexical = format(number, "f") if number else "0"
            if "." in lexical:
                lexical = lexical.rstrip("0").rstrip(".")
            return Literal(lexical, datatype=XSD.decimal, normalize=False)
        except InvalidOperation as error:
            raise ValueError("Invalid RDF numerical literal.") from error
    # RDF 1.1 simple literals and explicitly typed xsd:string are equivalent.
    if isinstance(term, Literal) and term.datatype == XSD.string:
        return Literal(str(term))
    return term


def parse_graph(document: Any) -> set[Triple]:
    """Expand JSON-LD and normalize local nodes and numerical literals.

    Parameters
    ----------
    document : dict
        JSON-LD object with an inline ``@context`` and an ``@graph`` array.

    Returns
    -------
    set of tuple
        Unique RDF triples. Local URIs become anonymous alignment variables.
        Equal finite numbers compare equally across RDF numerical datatypes.
    """
    if not isinstance(document, dict):
        raise ValueError("Expected a JSON-LD object, not a JSON-encoded string.")
    if not isinstance(document.get("@context"), dict):
        raise ValueError("A shared inline @context object is required.")
    if not isinstance(document.get("@graph"), list):
        raise ValueError("An @graph array is required.")
    if "@id" in document:
        raise ValueError("A named root graph is not supported; omit the root @id.")
    check_contexts(document)
    _reject_aliases(document)
    graph = Graph()
    try:
        graph.parse(
            data=json.dumps(document, allow_nan=False), format="json-ld", publicID=FALLBACK_BASE
        )
    except Exception as error:
        raise ValueError(f"Invalid JSON-LD: {error}") from error
    if len(graph) > 1000:
        raise ValueError("At most 1,000 triples per graph are supported.")
    return {tuple(_normalize(term) for term in triple) for triple in graph}


def align_graphs(
    predicted: set[Triple],
    reference: set[Triple],
    *,
    max_states: int = 100_000,
    max_seconds: float = 3.0,
) -> tuple[set[Triple], dict[Any, Any], bool, int]:
    """Maximize overlap under a partial injective mapping of local nodes.

    Branch-and-bound search preserves links between models and offers. If the
    search budget is exhausted, the returned overlap is a lower bound and
    ``exact`` is false; it must not be presented as an exact optimum.
    """
    gold_by_predicate: dict[Any, list[Triple]] = defaultdict(list)
    for triple in reference:
        gold_by_predicate[triple[1]].append(triple)
    nodes = {term for triple in predicted for term in triple if isinstance(term, BNode)}
    if len(nodes) > 100:
        raise ValueError("At most 100 local nodes per response are supported.")
    candidates: dict[Any, set[Any]] = {node: set() for node in nodes}
    compatible: dict[Triple, list[dict[Any, Any]]] = {}
    for triple in predicted:
        possible = []
        for target in gold_by_predicate[triple[1]]:
            pairs: dict[Any, Any] = {}
            reverse: dict[Any, Any] = {}
            for source, destination in zip(triple, target, strict=True):
                if isinstance(source, BNode):
                    if not isinstance(destination, BNode):
                        break
                    if source in pairs and pairs[source] != destination:
                        break
                    if destination in reverse and reverse[destination] != source:
                        break
                    pairs[source] = destination
                    reverse[destination] = source
                elif source != destination:
                    break
            else:
                possible.append(pairs)
                for source, destination in pairs.items():
                    candidates[source].add(destination)
        compatible[triple] = possible
    degree = Counter(t for triple in predicted for t in triple if isinstance(t, BNode))
    order = sorted(nodes, key=lambda n: (len(candidates[n]), -degree[n], str(n)))
    mapping: dict[Any, Any] = {}
    used: set[Any] = set()
    best_mapping: dict[Any, Any] = {node: None for node in nodes}
    best = sum(
        bool(options)
        for triple, options in compatible.items()
        if not any(isinstance(t, BNode) for t in triple)
    )
    states, exhausted = 0, False
    deadline = monotonic() + max_seconds

    def bound() -> int:
        count = 0
        for options in compatible.values():
            for pairs in options:
                if all(
                    (mapping[source] == target if source in mapping else target not in used)
                    for source, target in pairs.items()
                ):
                    count += 1
                    break
        return count

    def search(index: int) -> None:
        nonlocal best, best_mapping, states, exhausted
        if states >= max_states or monotonic() >= deadline:
            exhausted = True
            return
        states += 1
        upper = bound()
        if upper <= best:
            return
        if index == len(order):
            best, best_mapping = upper, dict(mapping)
            return
        source = order[index]
        # Try promising assignments first, followed by leaving this node unmatched.
        choices = []
        for target in sorted(candidates[source] - used, key=str):
            mapping[source] = target
            used.add(target)
            choices.append((bound(), target))
            used.remove(target)
        mapping.pop(source, None)
        for _, target in sorted(choices, key=lambda pair: -pair[0]) + [(0, None)]:
            mapping[source] = target
            if target is not None:
                used.add(target)
            search(index + 1)
            if target is not None:
                used.remove(target)
            del mapping[source]
            if exhausted:
                return

    search(0)
    aligned = {
        tuple(
            best_mapping.get(t) or BNode("unmatched:" + str(t)) if isinstance(t, BNode) else t
            for t in triple
        )
        for triple in predicted
    }
    exact = not exhausted or best == min(len(predicted), len(reference))
    return aligned, best_mapping, exact, states


def display_term(term: Any) -> str:
    """Return a readable RDF term without changing its comparison semantics."""
    if isinstance(term, BNode):
        return "_:" + str(term)
    if isinstance(term, URIRef):
        for prefix, uri in {
            "kb": "https://keyboards.wikibase.cloud/entity/",
            "kbt": "https://keyboards.wikibase.cloud/prop/direct/",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        }.items():
            if str(term).startswith(uri):
                return prefix + ":" + str(term)[len(uri) :]
    return term.n3()


def score_graphs(prediction: Any, reference: Any) -> dict[str, Any]:
    """Compute triple precision, recall, F1 and an auditable aligned diff.

    Examples
    --------
    >>> doc = {"@context": {"kbt": "https://keyboards.wikibase.cloud/prop/direct/",
    ...                     "kb": "https://keyboards.wikibase.cloud/entity/"},
    ...        "@graph": [{"@id": "kb:Q18", "kbt:P1": 32}]}
    >>> score_graphs(doc, doc)["f1"]
    1.0
    """
    predicted, gold = parse_graph(prediction), parse_graph(reference)
    aligned, mapping, exact, states = align_graphs(predicted, gold)
    matched, extra, missing = aligned & gold, aligned - gold, gold - aligned
    tp, fp, fn = len(matched), len(extra), len(missing)
    precision = tp / (tp + fp) if tp + fp else (1.0 if not gold else 0.0)
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 1.0

    def rows(triples: set[Triple]) -> list[list[str]]:
        return sorted([list(map(display_term, triple)) for triple in triples])

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "predicted_triples": len(predicted),
        "reference_triples": len(gold),
        "exact": exact,
        "search_states": states,
        "alignment": [
            {
                "prediction": display_term(source),
                "reference": display_term(target) if target is not None else None,
            }
            for source, target in sorted(mapping.items(), key=lambda pair: str(pair[0]))
        ],
        "matched": rows(matched),
        "extra": rows(extra),
        "missing": rows(missing),
    }
