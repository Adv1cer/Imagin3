from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, DeclarativeBase


class Base(DeclarativeBase):
    pass


def get_engine(database_url: str):
    return create_engine(database_url, future=True)


@contextmanager
def session_scope(engine):
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
