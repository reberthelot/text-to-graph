"""Entity linking: surface string -> existing Wikibase id, or None.   <-- YOUR PART (step 2)

The assignment's rule: *reuse an existing identifier when a sufficiently
certain match exists; never invent one.* A wrong link costs more than no
link (a wrong ``kb:Q…`` is a false triple *and* a missing one), so this
module is deliberately conservative:

1. ``normalize_label`` maps the spelling variants of one name to one key
   (``"PSR-E-583"``, ``"psr e583"``, ``"PSR-E583"``);
2. ``link_entity`` compares that key with the label and aliases of the
   catalogue entities **of the requested kind** only, and returns an id only
   when the best match designates exactly **one** entity.

Contract: ``tests/test_linking.py`` (real catalogue snapshot, no network).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable

from .catalogue import Catalogue, CatalogueEntity
from .vocabulary import EntityKind

# SPARQL 1.1 ECHAR (grammar rule [160]). The backslash comes first so the
# backslashes added for the other characters are not escaped a second time.
_ECHAR = {
    "\\": "\\\\",
    '"': '\\"',
    "'": "\\'",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
}
# SPARQL LANGTAG (rule [145]): the tag is also pasted into the query, so it
# must be validated too, not only the label.
_LANGTAG = re.compile(r"[a-zA-Z]+(-[a-zA-Z0-9]+)*")

# Any run of non-alphanumeric characters (Unicode-aware: keeps ø, æ, å).
# `_` is part of \w, so it is removed explicitly.
_NON_ALNUM = re.compile(r"[\W_]+")

# Trailing legal form of a company name ("Digitalpiano.com A/S" -> "Digitalpiano.com").
# Domain endings (.com, .dk) are part of the brand, not a legal form: they stay.
_LEGAL_SUFFIX = re.compile(
    r"[\s,]+(?:A/S|ApS|I/S|K/S|P/S|GmbH|AG|AB|Ltd\.?|Inc\.?|LLC|Co\.?)\s*$",
    re.IGNORECASE,
)


def normalize_label(text: str) -> str:
    """Canonical matching key of a name.

    Two spellings of the same name must give the same key, two different
    names must not (``"Nord Stage 4 88"`` vs ``"Nord Stage 4 73"``).

    Examples
    --------
    The tests expect, among others::

        normalize_label("PSR-E-583") == normalize_label("psr e583")
        normalize_label("Rød") == normalize_label("rød")
    """
    text = unicodedata.normalize("NFKC", text).casefold()
    return _NON_ALNUM.sub("", text)


def _legal_key(text: str) -> str:
    """Relaxed key: ``normalize_label`` after dropping a trailing legal form.

    The suffix is removed on the *raw* text, where the word boundary is still
    visible (after normalization "...coma/s" would be "...comas").
    """
    return normalize_label(_LEGAL_SUFFIX.sub("", text))


def _manufacturer_prefixes(catalogue: Catalogue) -> list[tuple[re.Pattern[str], str]]:
    """One ``(prefix pattern, manufacturer id)`` per manufacturer name, longest first.

    Longest first so that "AKAI Professional MPK" loses "AKAI Professional",
    not only "AKAI". ``\\b`` stops "Korg" from eating the start of "Korgasm".
    """
    names = [(n, e.id) for e in catalogue.of_kind(EntityKind.MANUFACTURER) for n in e.names]
    names.sort(key=lambda pair: len(pair[0]), reverse=True)
    return [(re.compile(rf"^\s*{re.escape(n)}\b[\s:-]*", re.IGNORECASE), mid) for n, mid in names]


def _split_manufacturer(
    text: str, prefixes: list[tuple[re.Pattern[str], str]]
) -> tuple[str | None, str]:
    """``("kb:Q10", "Pa700")`` for ``"Korg Pa700"``; ``(None, text)`` without a known prefix."""
    for pattern, manufacturer_id in prefixes:
        if match := pattern.match(text):
            return manufacturer_id, text[match.end() :]
    return None, text


def link_entity(name: str | None, kind: EntityKind, catalogue: Catalogue) -> str | None:
    """Id (``"kb:Q…"``) of the catalogue entity of ``kind`` named ``name``.

    Parameters
    ----------
    name : str or None
        Surface string from the extraction (``None`` or blank -> ``None``).
    kind : EntityKind
        Only entities of this kind are candidates ("Yamaha" is a
        manufacturer, never a keyboard model).
    catalogue : Catalogue
        The existing entities (label + aliases).

    Returns
    -------
    str or None
        The id when exactly one entity matches at the best level of evidence
        (an English label beats an alias), else ``None`` (no match, or an
        ambiguous one: let the caller create a local node or omit the link).
    """
    if name is None or not normalize_label(name):
        return None
    candidates = catalogue.of_kind(kind)
    # Levels of evidence, strongest first: (key function, names compared).
    # Level 3 is relaxed and only reached when levels 1-2 found nothing.
    levels: tuple[tuple[Callable[[str], str], Callable[[CatalogueEntity], Iterable[str]]], ...] = (
        (normalize_label, lambda entity: (entity.label,)),  # 1. English label
        (normalize_label, lambda entity: entity.aliases),  # 2. aliases
        (_legal_key, lambda entity: entity.names),  # 3. without legal suffix
    )
    if kind is EntityKind.KEYBOARD_MODEL:
        prefixes = _manufacturer_prefixes(catalogue)
        query_maker, _ = _split_manufacturer(name, prefixes)

        def without_maker(text: str) -> str:
            return normalize_label(_split_manufacturer(text, prefixes)[1])

        def compatible_names(entity: CatalogueEntity) -> Iterable[str]:
            # "Casio FP-10" must never reach "Roland FP-10": once the prefix is
            # gone, the manufacturers named on both sides have to agree.
            if query_maker and entity.manufacturer not in (None, query_maker):
                return ()
            return entity.names

        levels += ((without_maker, compatible_names),)  # 4. without manufacturer prefix
    for to_key, names_of in levels:
        if not (key := to_key(name)):  # e.g. the name was only "A/S"
            continue
        ids = {
            entity.id for entity in candidates if any(to_key(n) == key for n in names_of(entity))
        }
        if ids:  # the best non-empty level decides, lower levels are never consulted
            return next(iter(ids)) if len(ids) == 1 else None
    return None
