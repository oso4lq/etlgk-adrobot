import json

import pytest

from app.core.config import Settings
from tools.keitaro_examples import EXAMPLES_DIR


@pytest.fixture
def keitaro_example():
    """Real Keitaro request/response pairs recorded by tools/keitaro_probe.py."""

    def load(name: str) -> dict:
        return json.loads((EXAMPLES_DIR / f"{name}.json").read_text(encoding="utf-8"))

    return load


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
