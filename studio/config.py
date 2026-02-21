from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field
from typing import Optional
import logging
import os
import sys

class Settings(BaseSettings):
    """
    Configuration Management for the Digital Nervous System.
    Implements 12-Factor App principles.
    """
    github_token: SecretStr = Field(default=SecretStr("mock-token"))
    github_repository: str = Field(default="google/jules-studio")
    jules_username: str = Field(default="google-jules")
    google_cloud_project: str = Field(default="mock-project")

    # Model Stratification Strategy
    thinking_model: str = "gemini-2.5-pro"
    doing_model: str = "gemini-2.5-flash"

    # RAG Configuration
    vector_store_path: str = Field(default="data/vector_store")

    # Polling Configuration
    jules_poll_interval: float = Field(
        default_factory=lambda: 0.1 if (
            os.getenv("PYTEST_CURRENT_TEST") or
            "pytest" in sys.modules or
            any("pytest" in arg for arg in sys.argv)
        ) else 600.0
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

_settings: Optional[Settings] = None

try:
    _settings = Settings()
except Exception as e:
    logging.warning(f"Could not initialize settings from environment: {e}. Using defaults/mocks.")
    _settings = Settings() # Fallback to defaults if possible

def get_settings() -> Settings:
    """Returns the singleton settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
