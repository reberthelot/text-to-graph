"""Configuration for the evaluation frontend.

``STUDENT_URL`` only provides the *default* endpoint shown in the UI: every
extraction request carries its own endpoint and timeout (``models.ExtractRequest``).
The frontend holds no secret.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Environment-driven configuration for the frontend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # the service's variables live in the same .env
    )

    student_url: str = "http://localhost:8000/v1/extract"
    # Text / JSON-LD test cases loaded by "Reload server dataset".
    dataset_path: Path = REPO_ROOT / "data" / "keyboards.txt"

    log_level: str = "INFO"


def get_settings() -> Settings:
    """Build a fresh ``Settings`` (never cached, so tests can override)."""
    return Settings()
