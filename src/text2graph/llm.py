"""Async client for the CampusAI OpenAI-compatible chat API.

We call ``POST {CAMPUSAI_API_URL}/chat/completions`` directly with ``httpx``
rather than through the ``openai`` SDK: one dependency fewer, and the wire
format (``model`` + ``messages`` in, ``choices[0].message.content`` out) is
small enough to read in full.

The ``httpx.AsyncClient`` is created once in the lifespan and shared, so
concurrent ``/v1/extract`` requests reuse pooled connections.

Copied from project 07 (``src/text2sparql/llm.py``), plus the ``ChatModel``
protocol implemented by both ``LLMClient`` and the tests' ``FakeLLM``.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from .config import Settings

logger = logging.getLogger(__name__)

Message = dict[str, str]


class ChatModel(Protocol):
    """What the pipeline needs from an LLM: one async chat completion."""

    async def complete(
        self, messages: list[Message], response_format: dict[str, Any] | None = None
    ) -> str: ...


class LLMNotConfiguredError(RuntimeError):
    """No API key: extraction cannot run."""


class LLMTimeoutError(RuntimeError):
    """The LLM did not answer within ``llm_timeout_seconds``."""


class LLMUnavailableError(RuntimeError):
    """The LLM endpoint is unreachable or returned an unusable response."""


class LLMClient:
    """Minimal chat-completions client bound to one model."""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._endpoint = settings.campusai_api_url.rstrip("/") + "/chat/completions"

    async def complete(
        self, messages: list[Message], response_format: dict[str, Any] | None = None
    ) -> str:
        """Return the assistant message for ``messages``.

        Parameters
        ----------
        messages : list of dict
            OpenAI-style chat messages.
        response_format : dict, optional
            Forwarded as-is (structured outputs), e.g.
            ``{"type": "json_schema", "json_schema": {...}}``. The answer is
            still returned as text: parsing is the caller's job.

        Raises
        ------
        LLMNotConfiguredError, LLMTimeoutError, LLMUnavailableError
            Typed errors mapped to HTTP 503 / 504 / 502 by the server.
        """
        api_key = self._settings.campusai_api_key.get_secret_value()
        if not api_key:
            raise LLMNotConfiguredError("CAMPUSAI_API_KEY is not set")

        payload: dict[str, Any] = {
            "model": self._settings.campusai_model,
            "messages": messages,
            "temperature": self._settings.llm_temperature,
            "max_tokens": self._settings.llm_max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        try:
            response = await self._http.post(
                self._endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=self._settings.llm_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("LLM call timed out") from exc
        except httpx.TransportError as exc:
            raise LLMUnavailableError("LLM endpoint unreachable") from exc

        if response.status_code >= 400:
            # The provider message goes to the log only (may leak internals).
            logger.error("LLM returned HTTP %d: %s", response.status_code, response.text[:300])
            raise LLMUnavailableError(f"LLM returned HTTP {response.status_code}")

        try:
            choice = response.json()["choices"][0]
            content = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMUnavailableError("LLM response has an unexpected shape") from exc

        # A reasoning model can spend the whole max_tokens budget thinking and
        # return content=None: never forward that as the string "None".
        if not content or not str(content).strip():
            logger.error("LLM returned no answer (finish_reason=%s)", choice.get("finish_reason"))
            raise LLMUnavailableError("LLM returned an empty answer")
        if choice.get("finish_reason") == "length":
            logger.warning("LLM answer truncated by max_tokens=%d", self._settings.llm_max_tokens)
        return str(content).strip()
