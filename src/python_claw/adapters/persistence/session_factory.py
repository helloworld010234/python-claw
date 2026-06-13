"""SQLAlchemy engine and session factories for the persistence adapter."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import Engine, event
from sqlalchemy import create_engine as _create_engine
from sqlalchemy.orm import Session, sessionmaker

from python_claw.config.settings import get_settings


def _is_sqlite(url: str) -> bool:
    """Return True when the database URL points to SQLite."""
    return url.startswith("sqlite://")


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    """Enable foreign-key enforcement for every SQLite connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_engine(url: str, *, echo: bool = False) -> Engine:
    """Create a sync SQLAlchemy engine with SQLite-specific pragmas."""
    engine = _create_engine(url, echo=echo, future=True)
    if _is_sqlite(url):
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def get_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    """Return a configured engine, defaulting to the application settings."""
    resolved_url = url or get_settings().database_url
    return create_engine(resolved_url, echo=echo)


def get_session_maker(engine: Engine) -> Callable[[], Session]:
    """Return a bound session factory."""
    return sessionmaker(bind=engine, expire_on_commit=False)
