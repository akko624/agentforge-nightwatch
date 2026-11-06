from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import get_settings


@lru_cache
def get_engine():
    url = get_settings().database_url
    if url.startswith("sqlite:///."):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, pool_pre_ping=True, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def sqlite_settings(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
    return engine


def session_factory():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db():
    with session_factory()() as session:
        yield session
