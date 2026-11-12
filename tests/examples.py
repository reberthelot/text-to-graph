"""The two worked examples of the assignment, as test data.

For each: the input text, the *ideal* LLM answer (an ``Extraction``), and the
expected JSON-LD of the assignment (only its UUID differs).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from src.text2graph.schema import Extraction, KeyboardModelFacts, OfferFacts

CONTEXT = {
    "kb": "https://keyboards.wikibase.cloud/entity/",
    "kbt": "https://keyboards.wikibase.cloud/prop/direct/",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
}

# --- Example 1: an offer (Danish advertisement) --------------------------------
EXAMPLE1_TEXT = """\
Jeg sælger mit røde Nord Stage 4 med 88 tangenter, da jeg ikke får det brugt nok. Det står i rigtig pæn stand med enkelte små brugsspor og har kun været brugt hjemme.

Der er separate sektioner til piano, orgel og synthesizer samt masser af muligheder for at justere lyde og effekter. Et godt instrument, men mere end jeg har brug for.

Kan afhentes og prøves i Odense efter aftale. Strømkabel medfølger. Prisen er uden stativ.

Sælges for 26.500 kr.

Annonce opdateret: 18. oktober 2026."""

# "Additional model specifications are omitted in this example": no model facts.
EXAMPLE1_EXTRACTION = Extraction(
    models=[KeyboardModelFacts(name="Nord Stage 4 88")],
    offers=[OfferFacts(model="Nord Stage 4 88", price_dkk=26500, date=dt.date(2026, 10, 18))],
)

EXAMPLE1_JSONLD: dict[str, Any] = {
    "@context": {
        "@base": "https://example.org/keyboards/extraction/57c94ee6-73bf-4a18-b8c1-4b29e62a307d/",
        **CONTEXT,
    },
    "@graph": [
        {
            "@id": "offer/1",
            "kbt:P11": {"@id": "kb:Q42"},
            "kbt:P24": {"@id": "kb:Q23"},
            "kbt:P25": 26500,
            "kbt:P26": {"@value": "2026-10-18", "@type": "http://www.w3.org/2001/XMLSchema#date"},
        }
    ],
}

# --- Example 2: two keyboard models (English specification text) ---------------
EXAMPLE2_TEXT = """\
The Yamaha PSR-E483 and PSR-E583 look like close relatives on paper, and choosing between these two keyboard models involves more than counting keys. Both have 61 touch-sensitive keys and can sound up to 64 notes simultaneously. The E483 offers 860 voices, while the E583 increases that selection to 890.

Neither model saves you any desk space over the other. Each measures 99.2 cm across, 40.4 cm from front to back and 13.6 cm high. The PSR-E483 is slightly lighter at 7.0 kg; the PSR-E583 weighs 7.3 kg. Those weights exclude batteries. If you are arranging delivery, avoid confusing the instrument dimensions with the packaging: both boxes measure 1068 × 500 × 216 mm in width, depth and height.

The sound systems are a more noticeable difference. Each keyboard contains two speakers with a diameter of 12 cm, but the E483 has two 6 W amplifier channels, compared with two 12 W channels on the E583. Despite that difference, Yamaha lists power consumption as 13 W for each model, using the PA-150C adaptor for the E483 and the PA-300C for the E583.

The physical audio connections are the same on both instruments: one headphone socket, two separate line-output sockets labelled L/L+R and R, one stereo mini-jack AUX input, and one microphone input. The stereo AUX connection is a single socket, not two inputs.

Both models also provide a USB Type-A connection for a flash drive and a USB Type-C connection to a computer. The computer connection supports a stereo USB audio interface at 44.1 kHz and 16 bits. The E583 adds a modulation wheel and support for an expression pedal, whereas the E483 has neither. Both can run on six AA batteries."""

_COMMON = {
    "manufacturer": "Yamaha",
    "keys": 61,
    "width_mm": 992,
    "depth_mm": 404,
    "height_mm": 136,
    "polyphony": 64,
    "loudspeakers": 2,
    "headphone_outputs": 1,
    "power_consumption_w": 13,
    "audio_outputs": 2,
    "microphone_inputs": 1,
    "audio_inputs": 1,
}
EXAMPLE2_EXTRACTION = Extraction(
    models=[
        KeyboardModelFacts(name="PSR-E483", weight_kg=7.0, **_COMMON),
        KeyboardModelFacts(name="PSR-E583", weight_kg=7.3, **_COMMON),
    ]
)


def _example2_model(local_id: str, label: str, weight: float) -> dict[str, Any]:
    return {
        "@id": local_id,
        "rdfs:label": {"@value": label, "@language": "en"},
        "kbt:P1": 61,
        "kbt:P2": 992,
        "kbt:P3": 404,
        "kbt:P4": 136,
        "kbt:P6": {"@id": "kb:Q2"},
        "kbt:P7": weight,
        "kbt:P8": 64,
        "kbt:P10": 2,
        "kbt:P11": {"@id": "kb:Q14"},
        "kbt:P13": 1,
        "kbt:P16": 13,
        "kbt:P20": 2,
        "kbt:P21": 1,
        "kbt:P22": 1,
    }


# "This example assumes that neither model has been matched to an existing
# catalogue item. Yamaha is linked to the existing manufacturer item kb:Q2."
EXAMPLE2_JSONLD: dict[str, Any] = {
    "@context": {
        "@base": "https://example.org/keyboards/extraction/8a3f6c21-9d47-4b82-a5e0-63c719d2f408/",
        **CONTEXT,
    },
    "@graph": [
        _example2_model("model/1", "PSR-E483", 7.0),
        _example2_model("model/2", "PSR-E583", 7.3),
    ],
}


def example2_with_catalogue_link() -> dict[str, Any]:
    """Example 2 as the *real* catalogue links it: PSR-E583 is ``kb:Q106``.

    The snapshot has ``PSR-E583`` as an alias of Q106, so a linked node
    replaces the local ``model/2`` (and loses its ``rdfs:label``).
    """
    e583 = _example2_model("kb:Q106", "PSR-E583", 7.3)
    del e583["rdfs:label"]
    return {
        "@context": EXAMPLE2_JSONLD["@context"],
        "@graph": [_example2_model("model/1", "PSR-E483", 7.0), e583],
    }
