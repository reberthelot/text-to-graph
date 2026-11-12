"""The text-to-graph pipeline: extract -> link -> build.

::

    text --LLM (prompts + schema)--> Extraction      (surface strings, mm/kg/W/DKK)
         --linking (catalogue)----> kb:Q… or None   (per model / manufacturer / colour / seller)
         --graph--------------------> JSON-LD          (@base = fresh UUID, local ids)

Each step is logged (``INFO``): the uvicorn log shows what the LLM extracted
and how every name was linked, which is where most errors are found.
"""

from __future__ import annotations

import logging
from typing import Any

from .catalogue import Catalogue
from .extraction import extract_facts
from .graph import build_jsonld
from .linking import link_entity
from .llm import ChatModel
from .vocabulary import EntityKind, new_base_iri

logger = logging.getLogger(__name__)


class TextToGraph:
    """Stateless apart from its collaborators: safe to share across requests."""

    def __init__(self, llm: ChatModel, catalogue: Catalogue) -> None:
        self.llm = llm
        self.catalogue = catalogue

    def link(self, name: str | None, kind: EntityKind) -> str | None:
        """``linking.link_entity`` bound to this catalogue, with a trace."""
        entity_id = link_entity(name, kind, self.catalogue)
        if name:
            logger.info("Link %-14s %r -> %s", kind, name, entity_id or "(none)")
        return entity_id

    async def run(self, text: str) -> dict[str, Any]:
        """JSON-LD document of the facts stated in ``text``."""
        # Application code (not the LLM) generates the extraction UUID.
        base = new_base_iri()
        extraction = await extract_facts(text, self.llm, self.catalogue)
        logger.info(
            "Extracted %d model(s), %d offer(s): %s",
            len(extraction.models),
            len(extraction.offers),
            extraction.model_dump_json(exclude_none=True),
        )
        document = build_jsonld(extraction, self.link, base)
        logger.info("Built %d node(s) under %s", len(document["@graph"]), base)
        return document
