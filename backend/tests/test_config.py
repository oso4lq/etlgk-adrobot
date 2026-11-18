import pytest
from pydantic import ValidationError

from app.core.config import (
    BACKEND_DIR,
    DEFAULT_DATABASE_URL,
    ENV_FILE,
    REPOSITORY_ROOT,
    DatabaseSettings,
    Settings,
)


def test_settings_require_keitaro_variables(monkeypatch):
    monkeypatch.delenv("KEITARO_BASE_URL", raising=False)
    monkeypatch.delenv("KEITARO_API_KEY", raising=False)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)
    message = str(error.value)
    assert "keitaro_base_url" in message
    assert "keitaro_api_key" in message


def test_missing_variable_error_does_not_echo_secrets(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "KEITARO_API_KEY=test-secret-key-123\nKEITARO_ADMIN_PASSWORD=admin-password-456\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("KEITARO_BASE_URL", raising=False)
    monkeypatch.delenv("KEITARO_API_KEY", raising=False)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=env_file)
    message = str(error.value)
    assert "keitaro_base_url" in message
    assert "test-secret-key-123" not in message
    assert "admin-password-456" not in message


def test_empty_required_variable_is_treated_as_missing(monkeypatch):
    monkeypatch.setenv("KEITARO_BASE_URL", "https://tracker.example.com")
    monkeypatch.setenv("KEITARO_API_KEY", "")
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)
    assert "keitaro_api_key" in str(error.value)


def test_empty_database_url_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    assert DatabaseSettings(_env_file=None).database_url == DEFAULT_DATABASE_URL


def test_api_key_is_hidden_in_repr(make_settings):
    settings = make_settings()
    assert "test-secret-key-123" not in repr(settings)
    assert "test-secret-key-123" not in str(settings.model_dump())
    assert settings.keitaro_api_key.get_secret_value() == "test-secret-key-123"


def test_base_url_trailing_slash_is_stripped(make_settings):
    assert make_settings().keitaro_base_url == "https://tracker.example.com"


def test_defaults(make_settings):
    settings = make_settings()
    assert settings.redirect_url == "https://google.com"
    assert settings.keitaro_write_name_prefix == ""
    assert settings.cors_origins == ["http://localhost:4200"]


def test_default_database_url_is_absolute_in_backend_dir():
    expected = (BACKEND_DIR / "adrobot.db").resolve().as_posix()
    assert f"sqlite:///{expected}" == DEFAULT_DATABASE_URL


def test_env_file_is_repository_root():
    assert ENV_FILE == REPOSITORY_ROOT / ".env"
    assert (REPOSITORY_ROOT / "CLAUDE.md").exists()
