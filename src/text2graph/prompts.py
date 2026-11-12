"""Extraction prompt: system instructions + few-shot examples.   <-- YOUR PART (step 4)

The LLM receives these messages together with the JSON Schema of
``schema.Extraction`` (``EXTRACTION_RESPONSE_FORMAT``): the schema fixes the
*shape* of the answer, this prompt teaches the *rules* (what to extract, what
to leave null, which units, how to name entities).

Contract (``tests/test_prompts.py``)::

    [{"role": "system", "content": SYSTEM_PROMPT (+ catalogue listing?)},
     {"role": "user", "content": <few-shot text 1>},
     {"role": "assistant", "content": <Extraction 1 as JSON>},
     ...                                            # >= 2 few-shot pairs
     {"role": "user", "content": <... text ...>}]  # the text to extract, verbatim

Tools already available:

* ``catalogue.prompt_listing()`` -- names (+ aliases) of the manufacturers,
  colours, sellers and keyboard models of the Wikibase, without ids;
* ``Extraction(...).model_dump_json()`` -- serialize a few-shot answer
  (instances are validated at import: a typo in a field name fails fast).
"""

from __future__ import annotations

import datetime as dt

from .catalogue import Catalogue
from .llm import Message
from .schema import Extraction, KeyboardModelFacts, OfferFacts

# Rules of the assignment made operational. Written in English, even for Danish
# inputs; the catalogue listing (names only, no ids) is appended at run time.
SYSTEM_PROMPT = """\
You are an information-extraction system for a knowledge graph about musical keyboards \
(digital pianos, synthesizers, arrangers, MIDI controllers, stage pianos, organs).
Read one English or Danish text and fill in the JSON schema with the keyboard models it \
describes and the offers (advertisements) it contains. Answer with the JSON object only.

General rules
- Extract only facts stated in the text. Never guess, never use outside knowledge about \
specifications.
- null means "not stated". Use 0 only when the text explicitly states an absence \
(e.g. "has no speakers", "all lack loudspeakers" -> loudspeakers = 0).
- If the text is not about musical keyboards (cars, motorcycles, watches, other products), \
return {"models": [], "offers": []}. A brand name such as "Yamaha" or "Casio" alone does \
not make the product a keyboard.
- Ignore facts that have no field in the schema (voices, styles, rhythms, USB Type-A or \
Type-C, batteries, amplifier wattage, speaker diameter...).

Units and numbers (the unit is implicit in the field name)
- Dimensions in mm (1 cm = 10 mm, 1 m = 1000 mm), weight in kg (1 g = 0.001 kg), power \
consumption in W, prices in DKK. "kr.", "kr", ",-" and "DKK" all mean DKK; do not convert \
other currencies.
- Danish number format: "." groups thousands and "," is the decimal mark: \
"26.500 kr." = 26500, "7,5 kg" = 7.5, "1.234,50" = 1234.5.
- Qualified values: keep the value, drop the qualifier ("4.6 kg without batteries" -> 4.6).
- Dimensions and weight are those of the instrument, never of the box or packaging.
- power_consumption_w is the consumption of the instrument (or of its adaptor), never the \
output power of the amplifiers or speakers.
- polyphony is the maximum number of simultaneous notes, never the number of voices/sounds.

Connectors: count physical sockets, not channels
- A stereo jack (AUX in, headphones) is one socket.
- headphone_outputs: headphone sockets. audio_outputs: dedicated line outputs \
(e.g. "L/MONO and R" = 2 sockets). A single socket documented as serving both purposes \
(e.g. "PHONES/OUTPUT") counts once in each field.
- microphone_inputs: microphone sockets; audio_inputs: other audio inputs (AUX, LINE IN).
- midi_in / midi_out / midi_through: 5-pin DIN MIDI sockets only (MIDI over USB is not a \
socket). usb_type_b: USB Type-B connectors ("USB TO HOST" with a Type-B plug).

Names and entities
- The catalogue below lists the known manufacturers, colours, sellers and keyboard models.
- Model name: if the text refers to a catalogue model, copy its catalogue name exactly, \
choosing the variant implied by the text (e.g. for a model sold with 73 or 88 keys, pick \
the variant whose key count is stated). If it matches no catalogue model, write the model \
name as it appears in the text, without adding words.
- If the text speaks about a whole family whose variants are all in the catalogue \
("the three versions of X"), output one entry per catalogue variant.
- A number that only appears inside a model name is not a stated fact: "Nord Piano 6 73" \
alone does not state keys = 73; fill keys only when the text itself gives the key count.
- manufacturer: the brand as written or implied by the model name (use the catalogue \
name or alias when possible). colour: the predominant colour of the instrument, in English, \
base form ("røde"/"rød" -> "red", "sort" -> "black", "hvid" -> "white").
- Every offer must reference a model: put the model in "models" (with its stated facts, \
or only its name) and copy that exact name into offer.model.

Offers
- An offer is a text in which someone sells a keyboard (shop page, classified ad).
- seller: the shop or organisation selling it (not a private person); null if not stated.
- price_dkk: the asking price, not the original purchase price.
- url: the URL of the advertisement if the text gives one; null otherwise.
- date: the advertisement date as YYYY-MM-DD; when an update date is stated \
("opdateret", "updated"), use the update date. Danish months: januar, februar, marts, \
april, maj, juni, juli, august, september, oktober, november, december.
"""

# Invented (text, ideal answer) pairs: never a text of data/keyboards.txt or of
# the assignment (the test checks it), otherwise the evaluation measures recall
# of the prompt instead of extraction. Each one shows a few hard cases.
FEW_SHOT_EXAMPLES: list[tuple[str, Extraction]] = [
    (
        # English spec sheet of a model absent from the catalogue (name as written):
        # cm -> mm, g -> kg, distractors (carton, amplifier W, tones), DIN MIDI
        # explicitly absent (0) vs MIDI over USB.
        "Spec sheet - Kawai ES120 digital piano. 88 weighted keys, 64-note maximum "
        "polyphony, 10 tones. Finish: white. Dimensions (W x D x H): 132.2 x 23.2 x 9.9 cm; "
        "shipping carton 145 x 33 x 20 cm. Weight: 10500 g (without the pedal). Two 8 W "
        "amplifiers drive two speakers; power consumption is 3 W with the supplied "
        "adaptor. Rear panel: one PHONES jack, one USB Type-B port (MIDI over USB only), "
        "sustain pedal input. There are no DIN MIDI sockets.",
        Extraction(
            models=[
                KeyboardModelFacts(
                    name="Kawai ES120",
                    manufacturer="Kawai",
                    colour="white",
                    keys=88,
                    width_mm=1322,
                    depth_mm=232,
                    height_mm=99,
                    weight_kg=10.5,
                    polyphony=64,
                    loudspeakers=2,
                    midi_in=0,
                    midi_out=0,
                    headphone_outputs=1,
                    power_consumption_w=3,
                    usb_type_b=1,
                )
            ]
        ),
    ),
    (
        # Danish classified ad of a catalogue model: the variant named by the key
        # count ("Korg Kross 2-61"), thousands separator, update date, inflected
        # colour, original purchase price as a distractor, a shop as seller.
        "Til salg: sort Korg Kross 2 med 61 tangenter, vejer kun 4,2 kg. Næsten som ny, "
        "købt for 7.995 kr. sidste år. Sælges for 5.250 kr. hos Aarhus Musikbørs. "
        "Oprettet 2. marts 2026, opdateret 14. april 2026. "
        "Se mere: https://www.example.dk/annonce/korg-kross-2-61",
        Extraction(
            models=[
                KeyboardModelFacts(
                    name="Korg Kross 2-61",
                    manufacturer="Korg",
                    colour="black",
                    keys=61,
                    weight_kg=4.2,
                )
            ],
            offers=[
                OfferFacts(
                    model="Korg Kross 2-61",
                    seller="Aarhus Musikbørs",
                    price_dkk=5250,
                    url="https://www.example.dk/annonce/korg-kross-2-61",
                    date=dt.date(2026, 4, 14),
                )
            ],
        ),
    ),
    (
        # Off-topic text sharing a brand with keyboards: nothing to extract.
        "The new Casio G-Shock GA-2100 watch is water resistant to 200 m and weighs 51 g.",
        Extraction(),
    ),
]


def build_extraction_messages(text: str, catalogue: Catalogue) -> list[Message]:
    """Chat messages asking the LLM to extract the facts of ``text``.

    Parameters
    ----------
    text : str
        Input text (English or Danish), copied verbatim into the last message.
    catalogue : Catalogue
        Existing Wikibase entities, e.g. to list the canonical model names.

    Returns
    -------
    list of dict
        ``system``, then alternating ``user`` / ``assistant`` few-shot turns,
        then the final ``user`` turn containing ``text``.
    """
    system = f"{SYSTEM_PROMPT}\nCatalogue\n{catalogue.prompt_listing()}"
    messages: list[Message] = [{"role": "system", "content": system}]
    for shot_text, answer in FEW_SHOT_EXAMPLES:
        messages.append({"role": "user", "content": shot_text})
        messages.append({"role": "assistant", "content": answer.model_dump_json()})
    messages.append({"role": "user", "content": text})
    return messages
