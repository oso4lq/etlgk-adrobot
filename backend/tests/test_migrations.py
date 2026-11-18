from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.config import BACKEND_DIR, DEFAULT_DATABASE_URL, DatabaseSettings


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
    assert current_revision(url) == "0001"

    command.downgrade(alembic_config(url), "base")
    assert current_revision(url) is None

    command.upgrade(alembic_config(url), "head")
    assert current_revision(url) == "0001"


def test_migrations_accept_percent_in_database_url(tmp_path, monkeypatch):
    # Percent-encoded passwords (postgresql://user:p%40ss@...) must not break Alembic's config.
    folder = tmp_path / "100%"
    folder.mkdir()
    url = f"sqlite:///{(folder / 'migrations.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    assert current_revision(url) == "0001"


def test_database_settings_do_not_require_keitaro(monkeypatch):
    monkeypatch.delenv("KEITARO_BASE_URL", raising=False)
    monkeypatch.delenv("KEITARO_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = DatabaseSettings(_env_file=None)
    assert settings.database_url == DEFAULT_DATABASE_URL
