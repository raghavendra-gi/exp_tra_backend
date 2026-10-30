"""
Alembic environment.

Used both by the `alembic` command line and by migrate.py at app start-up.
When migrate.py calls it, it hands over an already-open connection (which
holds the migration lock), passed in config.attributes["connection"].
"""
import os
import sys

from alembic import context
from sqlalchemy import pool, create_engine

# Make the flat app modules (config, database, models) importable when the
# `alembic` CLI is run from the app/ folder.
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from config import settings  # noqa: E402
from database import Base    # noqa: E402
import models                # noqa: E402,F401  (registers every table on Base.metadata)

config = context.config
target_metadata = Base.metadata


def _configure(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        # SQLite can't ALTER most things in place; batch mode copies the table.
        render_as_batch=connection.dialect.name == "sqlite",
    )


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql` — print the SQL instead of running it."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        # Called from migrate.py with its own (locked) connection.
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    with engine.connect() as conn:
        _configure(conn)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
