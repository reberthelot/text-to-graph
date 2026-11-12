"""Configuration for the text2graph service.

Every value comes from the environment (or ``.env`` in local development) and
is validated at startup, so misconfiguration fails fast with a readable
``ValidationError`` instead of at the first request (GUIDE section 5).

The ``CAMPUSAI_*`` names are those of the assignment's snippet.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Environment-driven configuration for the text2graph service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # tolerate unrelated container env vars
    )

    # --- LLM (CampusAI, OpenAI-compatible chat API) ---------------------
    # SecretStr: the key is masked in every repr/log line.
    campusai_api_key: SecretStr = SecretStr("")
    campusai_api_url: str = "https://api.campusai.compute.dtu.dk/v1"
    campusai_model: str = "cai"
    # Not used by the baseline; available for embedding-based linking (bonus).
    campusai_embed_model: str = ""
    llm_timeout_seconds: float = Field(default=90.0, gt=0.0)
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    # A long specification sheet produces a long JSON answer; reasoning
    # models also spend hidden tokens from this budget (see project 06).
    llm_max_tokens: int = Field(default=4096, ge=256, le=16384)

    # --- entity linking ---------------------------------------------------
    # Snapshot of the Wikibase entities (scripts/fetch_catalogue.py).
    catalogue_path: Path = REPO_ROOT / "data" / "catalogue.json"

    # --- runtime ---------------------------------------------------------
    log_level: str = "INFO"


def get_settings() -> Settings:
    """Build and return a fresh ``Settings`` instance.

    Called explicitly (never cached at module import) so tests can override
    environment variables before the configuration is read.
    """
    return Settings()
