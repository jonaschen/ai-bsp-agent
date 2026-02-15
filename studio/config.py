from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field
from typing import Optional
import logging

class Settings(BaseSettings):
    """
    Configuration Management for the Digital Nervous System.
    Implements 12-Factor App principles.
    """
    github_token: SecretStr = Field(default=SecretStr("mock-token"))
    google_cloud_project: str = Field(default="mock-project")

    # Model Stratification Strategy
    thinking_model: str = "gemini-1.5-pro"
    doing_model: str = "gemini-1.5-flash"

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
    return _settings
