from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_DIR.parent
# One .env for the whole repository: the backend can be launched from any working directory.
ENV_FILE = REPOSITORY_ROOT / ".env"
# Absolute path, so the database location never depends on the current working directory.
DEFAULT_DATABASE_URL = f"sqlite:///{(BACKEND_DIR / 'adrobot.db').resolve().as_posix()}"


class DatabaseSettings(BaseSettings):
    """Only what migrations need: Alembic must work without Keitaro credentials."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        # Validation errors would otherwise echo every value from .env, secrets included.
        hide_input_in_errors=True,
        # "KEY=" means "not set": a required key fails loudly, an optional one keeps its default.
        env_ignore_empty=True,
    )

    database_url: str = DEFAULT_DATABASE_URL


class Settings(DatabaseSettings):
    keitaro_base_url: str
    keitaro_api_key: SecretStr
    keitaro_timeout_seconds: float = 10.0
    keitaro_max_retries: int = 2
    keitaro_write_name_prefix: str = ""

    campaign_domain: str = ""
    campaign_group: str = ""
    campaign_traffic_source: str = ""
    redirect_url: str = "https://google.com"

    offers_cache_ttl_seconds: int = 300
    cors_origins: list[str] = ["http://localhost:4200"]

    @field_validator("keitaro_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
