"""Intermediate extraction schema: what the LLM fills in (structured outputs).

The LLM never writes JSON-LD. It fills this flat, typed schema with *surface
strings* (``"Nord"``, ``"røde"`` → ``"red"``) and *numbers in the target units*;
the application then links the strings to catalogue ids (``linking.py``) and
builds the RDF graph (``graph.py``). Splitting the job this way keeps every
identifier (``kb:Q…``, ``model/1``, the UUID ``@base``) out of the LLM's hands:
it cannot invent a Wikibase id or a malformed JSON-LD document.

Two rules shape the schema:

* ``None`` means **not stated** in the text, never zero / false. ``0`` is a
  real value ("all lack loudspeakers").
* The JSON Schema sent to the LLM (``EXTRACTION_RESPONSE_FORMAT``) marks every
  field as required (strict structured outputs), while Python-side validation
  stays tolerant (missing keys default to ``None`` / ``[]``) in case a backend
  ignores the schema.

The docstrings and ``Field(description=...)`` are part of the JSON Schema:
they are written **for the LLM**.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    # extra="forbid" -> "additionalProperties": false in the JSON Schema.
    # serialization_defaults_required -> fields with a default are still
    # listed as "required" in the serialization-mode schema (strict mode).
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class KeyboardModelFacts(_Strict):
    """One keyboard model described in the text, with the facts stated about it.

    Every numerical field is null unless the text states it. Convert to the
    unit in the field name (cm -> mm, g -> kg). Count physical sockets, not
    audio channels.
    """

    name: str = Field(
        description="Model name. If it is a catalogue model, copy the catalogue "
        "name exactly; otherwise the name as written in the text."
    )
    manufacturer: str | None = Field(default=None, description="Manufacturer name")
    colour: str | None = Field(default=None, description="Predominant colour, in English")
    keys: int | None = Field(default=None, description="Number of keys")
    width_mm: float | None = Field(default=None, description="Width of the instrument in mm")
    depth_mm: float | None = Field(default=None, description="Depth (front to back) in mm")
    height_mm: float | None = Field(default=None, description="Height in mm")
    weight_kg: float | None = Field(default=None, description="Weight in kg")
    polyphony: int | None = Field(default=None, description="Maximum polyphony (notes)")
    loudspeakers: int | None = Field(default=None, description="Number of loudspeakers")
    midi_in: int | None = Field(default=None, description="MIDI IN DIN sockets")
    headphone_outputs: int | None = Field(default=None, description="Headphone sockets")
    midi_out: int | None = Field(default=None, description="MIDI OUT DIN sockets")
    midi_through: int | None = Field(default=None, description="MIDI THRU DIN sockets")
    power_consumption_w: float | None = Field(default=None, description="Power consumption in W")
    audio_outputs: int | None = Field(
        default=None, description="Dedicated line-output sockets (headphone sockets excluded)"
    )
    microphone_inputs: int | None = Field(default=None, description="Microphone input sockets")
    audio_inputs: int | None = Field(
        default=None, description="Audio input sockets other than microphone inputs (e.g. AUX)"
    )
    usb_type_b: int | None = Field(default=None, description="USB Type B connectors")


class OfferFacts(_Strict):
    """One offer (advertisement) to sell a keyboard model."""

    model: str = Field(
        description="Keyboard model on sale: exactly the `name` of one entry of `models`"
    )
    seller: str | None = Field(default=None, description="Shop or organisation selling it")
    price_dkk: float | None = Field(default=None, description="Asking price in DKK ('kr.')")
    url: str | None = Field(default=None, description="URL of the advertisement")
    # dt.date, not date: the field name would shadow the type in the class body.
    date: dt.date | None = Field(
        default=None, description="Advertisement date, YYYY-MM-DD; the update date when stated"
    )


class Extraction(_Strict):
    """All keyboard models and offers described in the text (both lists may be empty)."""

    models: list[KeyboardModelFacts] = Field(default_factory=list)
    offers: list[OfferFacts] = Field(default_factory=list)


def _strip_defaults(node: Any) -> Any:
    """Remove ``default`` keywords: strict structured outputs reject them."""
    if isinstance(node, dict):
        return {key: _strip_defaults(value) for key, value in node.items() if key != "default"}
    if isinstance(node, list):
        return [_strip_defaults(item) for item in node]
    return node


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema of ``model`` with every property required and no defaults.

    Examples
    --------
    >>> schema = strict_json_schema(OfferFacts)
    >>> sorted(schema["required"]) == sorted(schema["properties"])
    True
    >>> schema["additionalProperties"]
    False
    """
    return _strip_defaults(model.model_json_schema(mode="serialization"))


EXTRACTION_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "keyboard_extraction",
        "strict": True,
        "schema": strict_json_schema(Extraction),
    },
}
