from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import DatabaseSettings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# The URL never goes through config.set_main_option(): configparser treats "%" as interpolation,
# and percent-encoded passwords (postgresql://user:p%40ss@...) would break migrations.
# Tests pass their URL via config.attributes; otherwise DatabaseSettings is used, which
# (unlike Settings) does not require Keitaro credentials just to run migrations.
database_url = config.attributes.get("database_url") or DatabaseSettings().database_url

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Deliberately not app.db.session.create_db_engine: that one turns on SQLite foreign keys,
    # and batch mode recreates tables, which with FKs on would fail or cascade-delete rows.
    connectable = create_engine(database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # Batch mode lets Alembic alter tables on SQLite (it recreates them under the hood).
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
