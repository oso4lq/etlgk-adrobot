import pytest

from app.core.config import Settings


@pytest.fixture
def make_settings(tmp_path):
    """Builds settings without reading the real .env, so tests never touch real secrets."""

    def factory(**overrides) -> Settings:
        values = {
            "keitaro_base_url": "https://tracker.example.com/",
            "keitaro_api_key": "test-secret-key-123",
            "database_url": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)

    return factory
