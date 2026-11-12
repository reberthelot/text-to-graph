"""Network-free stand-ins (GUIDE section 8).

* ``FakeLLM``: scripted answers, records every ``messages`` list it receives.
* ``table_linker``: a dict-backed ``graph.Linker``, so ``graph.py`` can be
  tested without (and before) ``linking.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from src.text2graph.graph import Linker
from src.text2graph.vocabulary import EntityKind


class FakeLLM:
    """Drop-in replacement for ``LLMClient``.

    Parameters
    ----------
    answers : str or sequence of str
        Returned in order by successive ``complete`` calls; the last one is
        repeated once the script is exhausted.
    """

    def __init__(self, answers: str | Sequence[str]) -> None:
        self._answers = [answers] if isinstance(answers, str) else list(answers)
        self.calls: list[list[dict[str, str]]] = []
        self.response_formats: list[dict[str, Any] | None] = []

    async def complete(
        self, messages: list[dict[str, str]], response_format: dict[str, Any] | None = None
    ) -> str:
        self.calls.append(messages)
        self.response_formats.append(response_format)
        return self._answers[min(len(self.calls), len(self._answers)) - 1]


def table_linker(table: dict[tuple[EntityKind, str], str]) -> Linker:
    """Linker answering from ``{(kind, name): "kb:Q…"}``; anything else -> ``None``."""

    def link(name: str | None, kind: EntityKind) -> str | None:
        return table.get((kind, name)) if name else None

    return link
