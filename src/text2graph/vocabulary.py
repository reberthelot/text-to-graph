"""Vocabulary of the Keyboards Wikibase: namespaces, classes, property mapping.

Everything the graph builder needs to *name* things lives here, so
``graph.py`` only decides *which* triples to emit. The property ids come from
the live Wikibase (``kbt:P1`` = keys, ...), see the property query in the
assignment and ``README.md``.

The intermediate extraction schema (``schema.py``) uses readable field names
(``width_mm``); ``MODEL_QUANTITIES`` maps them to the Wikibase properties.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import uuid4

# --- namespaces ----------------------------------------------------------------
KB = "https://keyboards.wikibase.cloud/entity/"
KBT = "https://keyboards.wikibase.cloud/prop/direct/"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
XSD_DATE = "http://www.w3.org/2001/XMLSchema#date"

# Every extraction gets its own base IRI below this root (assignment rule).
EXTRACTION_ROOT = "https://example.org/keyboards/extraction/"


class EntityKind(StrEnum):
    """Classes of the catalogue entities we link against."""

    MANUFACTURER = "manufacturer"
    KEYBOARD_MODEL = "keyboard_model"
    COLOUR = "colour"
    SELLER = "seller"
    COUNTRY = "country"


# Class item of each kind (``?item kbt:P11 ?class``).
CLASS_IDS: dict[EntityKind, str] = {
    EntityKind.MANUFACTURER: "kb:Q11",
    EntityKind.KEYBOARD_MODEL: "kb:Q14",
    EntityKind.COUNTRY: "kb:Q28",
    EntityKind.SELLER: "kb:Q37",
    EntityKind.COLOUR: "kb:Q79",
}

# --- classes and structural properties ---------------------------------------
INSTANCE_OF = "kbt:P11"
KEYBOARD_MODEL_CLASS = "kb:Q14"
OFFER_CLASS = "kb:Q42"
LABEL = "rdfs:label"

# --- keyboard model -------------------------------------------------------------
# Numerical facts: extraction field -> property. Units are implicit (mm, kg, W).
MODEL_QUANTITIES: dict[str, str] = {
    "keys": "kbt:P1",
    "width_mm": "kbt:P2",
    "depth_mm": "kbt:P3",
    "height_mm": "kbt:P4",
    "weight_kg": "kbt:P7",
    "polyphony": "kbt:P8",
    "loudspeakers": "kbt:P10",
    "midi_in": "kbt:P12",
    "headphone_outputs": "kbt:P13",
    "midi_out": "kbt:P14",
    "midi_through": "kbt:P15",
    "power_consumption_w": "kbt:P16",
    "audio_outputs": "kbt:P20",
    "microphone_inputs": "kbt:P21",
    "audio_inputs": "kbt:P22",
    "usb_type_b": "kbt:P29",
}

# Item-valued facts: extraction field -> (property, kind of the linked entity).
MODEL_LINKS: dict[str, tuple[str, EntityKind]] = {
    "manufacturer": ("kbt:P6", EntityKind.MANUFACTURER),
    "colour": ("kbt:P9", EntityKind.COLOUR),
}

# --- offer -----------------------------------------------------------------------
OFFER_SELLER = "kbt:P23"  # item (seller)
OFFER_MODEL = "kbt:P24"  # item or local node (keyboard model on sale)
OFFER_PRICE = "kbt:P25"  # number, implicitly DKK
OFFER_URL = "kbt:P5"  # IRI: {"@id": url}
OFFER_DATE = "kbt:P26"  # {"@value": "YYYY-MM-DD", "@type": XSD_DATE}


def jsonld_context(base: str) -> dict[str, str]:
    """Shared ``@context`` of every response.

    Examples
    --------
    >>> jsonld_context("https://example.org/keyboards/extraction/x/")["kbt"]
    'https://keyboards.wikibase.cloud/prop/direct/'
    """
    return {"@base": base, "kb": KB, "kbt": KBT, "rdfs": RDFS}


def new_base_iri() -> str:
    """Fresh ``@base`` for one extraction: ``EXTRACTION_ROOT + uuid4 + '/'``.

    Examples
    --------
    >>> base = new_base_iri()
    >>> base.startswith(EXTRACTION_ROOT) and base.endswith("/")
    True
    >>> new_base_iri() != base
    True
    """
    return f"{EXTRACTION_ROOT}{uuid4()}/"


def empty_document(base: str) -> dict[str, Any]:
    """A valid JSON-LD response with no facts (``"@graph": []``)."""
    return {"@context": jsonld_context(base), "@graph": []}
