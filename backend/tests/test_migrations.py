from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.core.config import BACKEND_DIR, DEFAULT_DATABASE_URL, DatabaseSettings
from app.db import models  # noqa: F401  (registers tables in Base.metadata)
from app.db.base import Base


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.attributes["database_url"] = database_url
    return config


def current_revision(database_url: str) -> str | None:
    engine = create_engine(database_url)
    try:
        if not inspect(engine).has_table("alembic_version"):
            return None
        with engine.connect() as connection:
            query = text("SELECT version_num FROM alembic_version")
            return connection.execute(query).scalar_one_or_none()
    finally:
        engine.dispose()


def test_migrations_upgrade_and_downgrade(tmp_path):
    folder = tmp_path / "db with space"
    folder.mkdir()
    url = f"sqlite:///{(folder / 'migrations.db').as_posix()}"

    command.upgrade(alembic_config(url), "head")
    assert current_revision(url) == "0003"

    command.downgrade(alembic_config(url), "base")
    assert current_revision(url) is None

    command.upgrade(alembic_config(url), "head")
    assert current_revision(url) == "0003"


def test_migrations_accept_percent_in_database_url(tmp_path, monkeypatch):
    # Percent-encoded passwords (postgresql://user:p%40ss@...) must not break Alembic's config.
    folder = tmp_path / "100%"
    folder.mkdir()
    url = f"sqlite:///{(folder / 'migrations.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    assert current_revision(url) == "0003"


def test_database_settings_do_not_require_keitaro(monkeypatch):
    monkeypatch.delenv("KEITARO_BASE_URL", raising=False)
    monkeypatch.delenv("KEITARO_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = DatabaseSettings(_env_file=None)
    assert settings.database_url == DEFAULT_DATABASE_URL


def test_created_campaigns_table_follows_migrations(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    command.upgrade(alembic_config(url), "head")
    engine = create_engine(url)
    try:
        columns = {c["name"] for c in inspect(engine).get_columns("created_campaigns")}
    finally:
        engine.dispose()
    assert {
        "name",
        "alias",
        "country",
        "offer_id",
        "status",
        "keitaro_campaign_id",
        "country_stream_id",
        "offers_stream_id",
        "campaign_url",
        "error",
        "created_at",
        "updated_at",
    } <= columns

    command.downgrade(alembic_config(url), "0001")
    engine = create_engine(url)
    try:
        assert not inspect(engine).has_table("created_campaigns")
    finally:
        engine.dispose()


def test_editor_tables_follow_migrations(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    command.upgrade(alembic_config(url), "head")
    expected_columns = {
        "editor_campaigns": {"id", "keitaro_campaign_id", "name", "last_fetched_at"},
        "editor_streams": {"id", "campaign_id", "keitaro_stream_id", "name", "position"},
        "stream_offers": {
            "id",
            "stream_id",
            "keitaro_offer_id",
            "offer_name",
            "sort_order",
            "status",
            "weight",
            "is_pinned",
            "published_status",
            "published_weight",
        },
    }
    engine = create_engine(url)
    try:
        for table, columns in expected_columns.items():
            assert columns == {c["name"] for c in inspect(engine).get_columns(table)}
    finally:
        engine.dispose()

    command.downgrade(alembic_config(url), "0002")
    engine = create_engine(url)
    try:
        for table in expected_columns:
            assert not inspect(engine).has_table(table)
        assert inspect(engine).has_table("created_campaigns")
    finally:
        engine.dispose()


def test_migrations_match_models(tmp_path):
    # A model change without a migration (or the reverse) must fail here, not in production.
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    command.upgrade(alembic_config(url), "head")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    finally:
        engine.dispose()
    assert differences == []
