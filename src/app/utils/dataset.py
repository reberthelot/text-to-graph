"""Test-dataset file format: text / JSON-LD pairs (teacher's logic, unchanged).

``data/keyboards.txt`` holds multiline input texts, each followed by a blank
line and its reference JSON-LD object. The editable copy lives in the
browser; ``dump_dataset`` writes it back in the same format.
"""

from __future__ import annotations

import json
import re
from typing import Any

Case = dict[str, Any]

_BOUNDARY = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)*[ \t]*(?=\{)")


def parse_dataset(content: str) -> list[Case]:
    """Read multiline text followed by a JSON-LD object, repeatedly.

    Parameters
    ----------
    content : str
        UTF-8 text containing text / JSON-LD pairs. Input text and JSON objects
        may themselves contain blank lines. A JSON object begins on a new line
        after a blank line; normal JSON decoding locates its end.

    Returns
    -------
    list of dict
        Records with ``name``, ``text`` and ``reference`` fields.

    Examples
    --------
    >>> cases = parse_dataset('Yamaha GS1 weighs 90 kg\\n\\n{"@context": {}, "@graph": []}')
    >>> cases[0]["name"], cases[0]["reference"]["@graph"]
    ('Yamaha GS1 weighs 90 kg', [])
    """
    content = content.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    records: list[Case] = []
    position = 0
    decoder = json.JSONDecoder()
    while content[position:].strip():
        match = _BOUNDARY.search(content, position)
        if match is None:
            raise ValueError(f"Case {len(records) + 1}: expected a blank line followed by JSON-LD.")
        text = content[position : match.start()].strip()
        if not text:
            raise ValueError(f"Case {len(records) + 1}: input text is empty.")
        try:
            reference, end = decoder.raw_decode(content, match.end())
        except json.JSONDecodeError as error:
            raise ValueError(f"Case {len(records) + 1}: {error}") from error
        if not isinstance(reference, dict) or not isinstance(reference.get("@graph"), list):
            raise ValueError(f"Case {len(records) + 1}: expected a JSON-LD object with @graph.")
        if (
            end < len(content)
            and content[end:].strip()
            and not re.match(r"[ \t]*\n[ \t]*\n", content[end:])
        ):
            raise ValueError(f"Case {len(records) + 1}: expected a blank line after JSON-LD.")
        records.append({"name": text.splitlines()[0][:80], "text": text, "reference": reference})
        position = end
    if not records:
        raise ValueError("The dataset is empty.")
    if len(records) > 500:
        raise ValueError("At most 500 test cases are supported.")
    return records


def dump_dataset(records: list[Case]) -> str:
    """Serialize editable cases in the original text / JSON-LD format."""
    return (
        "\n\n".join(
            record["text"].strip()
            + "\n\n"
            + json.dumps(record["reference"], indent=2, ensure_ascii=False)
            for record in records
        )
        + "\n"
    )
