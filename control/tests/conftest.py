import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from imagin.db import Base


def test_database_url() -> str:
    """Derive the *_test database URL from DATABASE_URL.

    NOTE (patched 2026-07-22, third pass): the original draft of this helper
    did `DATABASE_URL.replace("/imagin", "/imagin_test")`. In a real
    docker-compose URL like
    postgresql+psycopg2://imagin:imagin@postgres:5432/imagin, the substring
    "/imagin" occurs TWICE — once inside "://imagin" (the username, because
    "//" + "imagin" contains "/imagin") and once at the end (the actual
    database name). str.replace() with no count silently rewrites both,
    turning the username into "imagin_test" too — a role that doesn't exist
    — which fails with "password authentication failed for user
    'imagin_test'" / "Role 'imagin_test' does not exist". This was caught
    running against a real docker-compose Postgres; the agent's own
    embedded-Postgres sandbox verification used a differently-shaped URL
    that happened not to trigger the double match, so it went undetected
    until then. Fixed by operating structurally on the URL's rightmost path
    segment (the database name) instead of a naive substring replace, so it
    cannot also match anything in the userinfo/host portion.
    """
    url = os.environ["DATABASE_URL"]
    base, sep, query = url.partition("?")
    path, _, _dbname = base.rpartition("/")
    return f"{path}/imagin_test{sep}{query}"


@pytest.fixture()
def db_session():
    database_url = test_database_url()
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)  # test-only convenience; real app uses Alembic (§8.5)
    session = Session(engine)
    yield session
    session.rollback()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()
