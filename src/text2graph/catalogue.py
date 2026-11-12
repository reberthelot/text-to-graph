"""Linking catalogue: the existing Wikibase entities we may reuse.

Loaded once (in the lifespan) from ``data/catalogue.json``, a snapshot of the
live Wikibase made by ``scripts/fetch_catalogue.py``. Each entity keeps its
English ``label`` and its ``aliases`` (``skos:altLabel`` + labels in other
languages, e.g. ``rød`` for red).

Data quirks worth knowing when you write ``linking.py``:

* some aliases are shared by two entities (``Roland GO:KEYS 5`` is the label
  of Q85 *and* a wrong ``@mul`` label of Q84);
* some aliases repeat the label with another casing (``nord lead 4``);
* four keyboards (Q4, Q6, Q7, Q9) have no ``kbt:P11`` but are keyboard models.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from .vocabulary import EntityKind

# Kinds listed by ``prompt_listing``, in this order. Countries are not linked
# by the baseline (no country property on models or offers).
PROMPT_KINDS: tuple[EntityKind, ...] = (
    EntityKind.MANUFACTURER,
    EntityKind.COLOUR,
    EntityKind.SELLER,
    EntityKind.KEYBOARD_MODEL,
)
_TITLES = {
    EntityKind.MANUFACTURER: "Manufacturers",
    EntityKind.COLOUR: "Colours",
    EntityKind.SELLER: "Sellers",
    EntityKind.KEYBOARD_MODEL: "Keyboard models",
    EntityKind.COUNTRY: "Countries",
}


@dataclass(frozen=True, slots=True)
class CatalogueEntity:
    """One Wikibase item that may be linked to."""

    id: str  # short form, e.g. "kb:Q2"
    kind: EntityKind
    label: str  # English label
    aliases: tuple[str, ...] = field(default_factory=tuple)
    manufacturer: str | None = None  # "kb:Q…" for keyboard models, when known

    @property
    def names(self) -> tuple[str, ...]:
        """Label first, then aliases."""
        return (self.label, *self.aliases)


class Catalogue:
    """In-memory, read-only collection of ``CatalogueEntity``."""

    def __init__(self, entities: Iterable[CatalogueEntity]) -> None:
        self._entities = tuple(entities)
        self._by_id = {entity.id: entity for entity in self._entities}

    @classmethod
    def from_file(cls, path: Path) -> Catalogue:
        """Load the JSON snapshot written by ``scripts/fetch_catalogue.py``."""
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            CatalogueEntity(
                id=row["id"],
                kind=EntityKind(row["kind"]),
                label=row["label"],
                aliases=tuple(row.get("aliases", ())),
                manufacturer=row.get("manufacturer"),
            )
            for row in payload["entities"]
        )

    def __len__(self) -> int:
        return len(self._entities)

    def __iter__(self) -> Iterator[CatalogueEntity]:
        return iter(self._entities)

    def get(self, entity_id: str) -> CatalogueEntity | None:
        """Entity by short id (``"kb:Q2"``), or ``None``."""
        return self._by_id.get(entity_id)

    def of_kind(self, kind: EntityKind) -> list[CatalogueEntity]:
        """All entities of one kind, in catalogue order."""
        return [entity for entity in self._entities if entity.kind == kind]

    def prompt_listing(self, kinds: Iterable[EntityKind] = PROMPT_KINDS) -> str:
        """Plain-text list of the entity names, to paste into a prompt.

        Ids are deliberately left out: the LLM copies *names*, the
        application links them (it can never invent a ``kb:Q…`` id).

        Examples
        --------
        >>> cat = Catalogue([CatalogueEntity("kb:Q5", EntityKind.MANUFACTURER,
        ...                                  "Clavia DMI", ("Nord",))])
        >>> print(cat.prompt_listing([EntityKind.MANUFACTURER]))
        Manufacturers:
        - Clavia DMI (also: Nord)
        """
        blocks = []
        for kind in kinds:
            lines = [f"{_TITLES[kind]}:"]
            for entity in self.of_kind(kind):
                also = f" (also: {', '.join(entity.aliases)})" if entity.aliases else ""
                lines.append(f"- {entity.label}{also}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)
