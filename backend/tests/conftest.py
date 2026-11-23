import json
from itertools import count

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import models  # noqa: F401  (registers tables in Base.metadata)
from app.db.base import Base
from app.db.session import create_db_engine
from app.repositories.created_campaigns import CreatedCampaignsRepository
from app.repositories.editor import EditorRepository
from app.services.campaign_creator import CampaignCreator
from app.services.creator_references import CreatorReferenceResolver
from app.services.offer_catalog import OfferCatalog
from tests.fakes import FakeKeitaroClient
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


@pytest.fixture
def fake() -> FakeKeitaroClient:
    return FakeKeitaroClient()


@pytest.fixture
def journal(db_session) -> CreatedCampaignsRepository:
    return CreatedCampaignsRepository(db_session)


@pytest.fixture
def editor_repository(db_session) -> EditorRepository:
    return EditorRepository(db_session)


@pytest.fixture
def offer_catalog(fake) -> OfferCatalog:
    return OfferCatalog(fake, ttl_seconds=300)


@pytest.fixture
def creator_settings(make_settings) -> Settings:
    return make_settings(
        keitaro_write_name_prefix="test_oso4lq_",
        campaign_domain="kylovoa.com",
        campaign_group="FORTESTS",
        campaign_traffic_source="FORTESTS",
    )


@pytest.fixture
def creator(fake, creator_settings) -> CampaignCreator:
    aliases = (f"alias{number}" for number in count(1))
    return CampaignCreator(
        fake,
        OfferCatalog(fake, ttl_seconds=300),
        CreatorReferenceResolver(fake, creator_settings),
        creator_settings,
        generate_alias=lambda: next(aliases),
    )
