import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config import settings

# pool_pre_ping : test a pooled connection before use (avoids "server closed the
#                 connection" after the database idled - Neon suspends idle computes).
# pool_recycle  : replace connections older than 5 min before the server drops them.
#                 DB_POOL_PRE_PING=0 skips the extra "SELECT 1" per checkout
#                 on an always-on database.
# pool_size/max_overflow : enough for a small team without exhausting free-tier
#                 connection limits.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=os.getenv("DB_POOL_PRE_PING", "1") != "0",
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
)
# expire_on_commit=False: after commit the objects keep their values, so
# returning a just-saved expense needs no extra SELECT to reload it.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)
Base = declarative_base()
