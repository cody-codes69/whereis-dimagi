"""SQLAlchemy engine + session + raw-sqlite access for FTS setup.

Also registers a user-defined ``REGEXP`` function on every connection so we
can filter places in the DB instead of pulling them all into Python.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import settings


def _db_url() -> str:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{settings.db_path}"


engine = create_engine(
    _db_url(),
    echo=False,
    future=True,
    connect_args={"check_same_thread": False},
)


def _regexp(pattern: str, value: str | None) -> int:
    if value is None:
        return 0
    try:
        return 1 if re.search(pattern, value, flags=re.IGNORECASE) else 0
    except re.error:
        return 0


@event.listens_for(engine, "connect")
def _on_connect(dbapi_connection, _):  # noqa: ANN001
    cur = dbapi_connection.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.close()
    dbapi_connection.create_function("REGEXP", 2, _regexp)


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def raw_connection() -> sqlite3.Connection:
    """Borrow a raw sqlite connection (for FTS5 DDL)."""
    cx = sqlite3.connect(settings.db_path)
    cx.create_function("REGEXP", 2, _regexp)
    return cx
