"""
Centralized application configuration.

All values are loaded from environment variables (or a local .env file in
development). Nothing here should ever contain a real secret — see
`.env.example` at the repo root for the documented list of variables an
operator must set before running in production.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---
    APP_NAME: str = "SmartVision"
    ENVIRONMENT: Literal["development", "production", "test"] = "development"
    DEBUG: bool = True

    # --- Database ---
    # Example: postgresql+psycopg://smartvision:changeme@localhost:5432/smartvision
    DATABASE_URL: str = "postgresql+psycopg://smartvision:smartvision@localhost:5432/smartvision"

    # --- Auth / security ---
    # Generate with: python -c "import secrets; print(secrets.token_urlsafe(64))"
    SECRET_KEY: str = Field(default="dev-only-insecure-secret-change-me")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    # Comma-separated list of origins allowed to call the API from a browser.
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:4173"
    # Allow the dev-only first-admin bootstrap endpoint. Must be false in prod.
    ALLOW_DEV_BOOTSTRAP: bool = True

    # --- Login rate limiting ---
    LOGIN_RATE_LIMIT_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300

    # --- Evidence storage ---
    EVIDENCE_STORAGE_DIR: str = str(BACKEND_ROOT.parent / "evidence_storage")
    EVIDENCE_RETENTION_DAYS: int = 30

    # --- SMTP (optional; notifications degrade gracefully if unset) ---
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_ADDRESS: str | None = None
    SMTP_USE_TLS: bool = True
    PUBLIC_BASE_URL: str = "http://localhost:5173"

    # --- Vision worker ---
    INFERENCE_DEVICE: Literal["auto", "cpu", "cuda"] = "auto"
    DEFAULT_INFERENCE_FPS: float = 5.0

    @field_validator("CORS_ORIGINS")
    @classmethod
    def _non_empty_cors(cls, v: str) -> str:
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
