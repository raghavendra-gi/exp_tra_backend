"""
Bring the database schema up to date — `alembic upgrade head`, run from code.

Called by main.py at start-up, so deploying new code is all it takes:
Render restarts the service and the new migrations run before the first request.

Also runnable by hand from the app/ folder:   python migrate.py

On PostgreSQL a session-level advisory lock makes sure that if several
processes start at once (e.g. more than one uvicorn worker) only one of them
migrates; the others wait and then find nothing left to do.
"""
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from database import engine

log = logging.getLogger("uvicorn.error")

APP_DIR = Path(__file__).resolve().parent
MIGRATION_LOCK_ID = 74_211_029   # any constant number, shared by all instances


def _alembic_config(connection) -> Config:
    cfg = Config(str(APP_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(APP_DIR / "migrations"))
    cfg.attributes["connection"] = connection
    return cfg


def run_migrations() -> None:
    with engine.connect() as conn:
        is_pg = conn.dialect.name == "postgresql"
        if is_pg:
            conn.execute(text("SELECT pg_advisory_lock(:id)"), {"id": MIGRATION_LOCK_ID})
            conn.commit()
        try:
            command.upgrade(_alembic_config(conn), "head")
            conn.commit()
            log.info("Database schema is up to date.")
        finally:
            if is_pg:
                conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": MIGRATION_LOCK_ID})
                conn.commit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migrations()
    print("Migrations applied.")
