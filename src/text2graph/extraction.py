"""LLM extraction step: prompt -> chat completion -> validated ``Extraction``.

``parse_extraction`` is pure and tolerant: with structured outputs the answer
is already bare JSON, but a backend that ignores ``response_format`` may wrap
it in prose or Markdown fences.
"""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from .catalogue import Catalogue
from .errors import ExtractionError
from .llm import ChatModel
from .prompts import build_extraction_messages
from .schema import EXTRACTION_RESPONSE_FORMAT, Extraction

logger = logging.getLogger(__name__)


def parse_extraction(raw: str) -> Extraction:
    """Validate the first JSON object found in ``raw`` as an ``Extraction``.

    Raises
    ------
    ExtractionError
        No JSON object, truncated JSON, or a shape the schema rejects.

    Examples
    --------
    >>> parse_extraction('```json\\n{"models": [{"name": "Roland SH-101", "keys": 32}]}\\n```')
    ... # doctest: +ELLIPSIS
    Extraction(models=[KeyboardModelFacts(name='Roland SH-101', manufacturer=None, ...
    >>> parse_extraction('{"models": [], "offers": []}')
    Extraction(models=[], offers=[])
    """
    start = raw.find("{")
    if start < 0:
        raise ExtractionError("the LLM answer contains no JSON object")
    try:
        data, _ = json.JSONDecoder().raw_decode(raw, start)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"the LLM answer is not valid JSON ({exc.msg})") from exc
    try:
        return Extraction.model_validate(data)
    except ValidationError as exc:
        # Short, safe summary: field paths and messages, no input echo.
        problems = "; ".join(
            f"{'.'.join(map(str, error['loc']))}: {error['msg']}" for error in exc.errors()[:3]
        )
        raise ExtractionError(f"the LLM answer does not match the schema ({problems})") from exc


async def extract_facts(text: str, llm: ChatModel, catalogue: Catalogue) -> Extraction:
    """Ask the LLM for the models and offers of ``text`` (structured outputs)."""
    messages = build_extraction_messages(text, catalogue)
    raw = await llm.complete(messages, response_format=EXTRACTION_RESPONSE_FORMAT)
    logger.debug("LLM answer: %s", raw)
    return parse_extraction(raw)
