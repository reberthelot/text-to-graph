"""Domain errors raised by the pipeline steps, mapped to HTTP by the server.

Their messages are written by us, so the server can echo them to the client
safely (unlike arbitrary exception text).
"""

from __future__ import annotations


class ExtractionError(RuntimeError):
    """The LLM answer could not be turned into an ``Extraction`` (HTTP 502)."""
