import json

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import models  # noqa: F401  (registers tables in Base.metadata)
from app.db.base import Base
from app.db.session import create_db_engine
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


@pytest.fixture
def db_session(tmp_path):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'session.db').as_posix()}")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
