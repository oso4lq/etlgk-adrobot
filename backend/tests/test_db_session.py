from sqlalchemy import text

from app.db.session import create_db_engine, create_session_factory


def test_engine_works_with_space_in_path(tmp_path):
    folder = tmp_path / "folder with space"
    folder.mkdir()
    engine = create_db_engine(f"sqlite:///{(folder / 'app.db').as_posix()}")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def test_sqlite_foreign_keys_enabled(tmp_path):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'fk.db').as_posix()}")
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_session_factory_opens_sessions(tmp_path):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 's.db').as_posix()}")
    with create_session_factory(engine)() as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1
