import os
import pytest
from pydantic import SecretStr
from studio.config import Settings, get_settings

def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")

    settings = Settings()
    assert settings.github_token.get_secret_value() == "test-token"
    assert settings.google_cloud_project == "test-project"

def test_settings_singleton():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2

def test_model_stratification():
    settings = get_settings()
    assert settings.thinking_model == "gemini-2.5-pro"
    assert settings.doing_model == "gemini-2.5-flash"

def test_rag_configuration():
    settings = get_settings()
    assert settings.vector_store_path == "data/vector_store"
    assert settings.embedding_model == "textembedding-gecko@003"
    assert settings.context_window == 1000000
