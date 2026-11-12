"""Step 2 -- entity linking (``src/text2graph/linking.py``), on the real catalogue.

uv run pytest tests/test_linking.py -q -m "not bonus"
"""

from __future__ import annotations

import pytest

from src.text2graph.catalogue import Catalogue
from src.text2graph.linking import link_entity, normalize_label
from src.text2graph.vocabulary import EntityKind

M, K, C, S = (
    EntityKind.MANUFACTURER,
    EntityKind.KEYBOARD_MODEL,
    EntityKind.COLOUR,
    EntityKind.SELLER,
)

# --- normalize_label --------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("PSR-E-583", "PSR-E583"),
        ("PSR-E583", "psr e583"),
        ("  Roland   SH-101 ", "roland sh101"),
        ("GO:KEYS 3", "Go Keys 3"),
        ("Rød", "rød"),
    ],
)
def test_spelling_variants_share_a_key(a: str, b: str) -> None:
    assert normalize_label(a) == normalize_label(b)


@pytest.mark.parametrize(
    ("a", "b"),
    [("Nord Stage 4 88", "Nord Stage 4 73"), ("Korg minilogue", "Korg minilogue xd")],
)
def test_different_names_keep_different_keys(a: str, b: str) -> None:
    assert normalize_label(a) != normalize_label(b)


# --- link_entity: confident matches ---------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "name", "expected"),
    [
        (M, "Yamaha", "kb:Q2"),
        (M, "yamaha", "kb:Q2"),
        (M, "Roland", "kb:Q16"),
        (M, "Nord", "kb:Q5"),  # alias of Clavia DMI
        (M, "Clavia DMI", "kb:Q5"),
        (C, "red", "kb:Q104"),
        (C, "rød", "kb:Q104"),  # Danish label = alias
        (C, "Black", "kb:Q3"),
        (S, "Morsø Musikhus", "kb:Q70"),
        (S, "Digitalpiano.com A/S", "kb:Q38"),
        (K, "Yamaha PSR-E583", "kb:Q106"),
        (K, "PSR-E583", "kb:Q106"),  # alias
        (K, "Yamaha PSR-E-583", "kb:Q106"),  # spelling variant (dataset case)
        (K, "roland sh101", "kb:Q18"),
        (K, "Yamaha GS1", "kb:Q100"),
        (K, "Nord Stage 4 88", "kb:Q23"),
        (K, "Nord Organ 3", "kb:Q7"),  # no kbt:P11 in the Wikibase
        (K, "nord lead 4", "kb:Q89"),  # label and alias of the SAME entity: not ambiguous
    ],
)
def test_links_known_entities(
    catalogue: Catalogue, kind: EntityKind, name: str, expected: str
) -> None:
    assert link_entity(name, kind, catalogue) == expected


# --- link_entity: no confident match -> None --------------------------------------------


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        (M, "Behringer"),
        (C, "purple"),
        (S, "Thomann"),
        (K, "PSR-E483"),  # not in the catalogue -> local node
        (K, "Roland Jupiter-08"),  # close to Jupiter-6, but another model
        (K, "Nord Stage 4"),  # three variants (88 / 73 / Compact): which one?
        (K, "Yamaha"),  # kinds are not mixed...
        (M, "Nord Stage 4 88"),  # ...in either direction
    ],
)
def test_no_link_without_a_confident_match(
    catalogue: Catalogue, kind: EntityKind, name: str
) -> None:
    assert link_entity(name, kind, catalogue) is None


@pytest.mark.parametrize("name", [None, "", "   "])
def test_missing_names_are_not_linked(catalogue: Catalogue, name: str | None) -> None:
    assert link_entity(name, M, catalogue) is None


def test_english_label_beats_alias(catalogue: Catalogue) -> None:
    # "Roland GO:KEYS 5" is the label of Q85 but also a (wrong) @mul label of
    # Q84 in the Wikibase: the label is the stronger evidence.
    assert link_entity("Roland GO:KEYS 5", K, catalogue) == "kb:Q85"


# --- bonus ------------------------------------------------------------------------------


@pytest.mark.bonus
@pytest.mark.parametrize(
    ("kind", "name", "expected"),
    [
        (S, "Digitalpiano.com", "kb:Q38"),  # legal suffix "A/S" dropped (assignment table)
        (K, "Pa700", "kb:Q40"),  # catalogue label minus its manufacturer ("Korg Pa700")
        (K, "Arturia MiniLab 3", "kb:Q77"),  # query minus its manufacturer = alias "Minilab 3"
    ],
)
def test_bonus_harder_matches(
    catalogue: Catalogue, kind: EntityKind, name: str, expected: str
) -> None:
    assert link_entity(name, kind, catalogue) == expected
