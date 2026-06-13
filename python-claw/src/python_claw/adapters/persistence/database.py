"""Database connectivity primitives for the SQLAlchemy persistence adapter."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for typed SQLAlchemy declarative models."""


def _set_sqlite_pragma(dbapi_conn: object, _connection_record: object) -> None:
    """Enable SQLite foreign-key enforcement for every new DB-API connection."""
    import sqlite3

    if isinstance(dbapi_conn, sqlite3.Connection):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine for the configured database URL.

    SQLite engines automatically enable ``PRAGMA foreign_keys=ON`` so that
    declared foreign keys are actually enforced at runtime. PostgreSQL engines
    are returned unchanged.
    """
    engine = create_engine(database_url, echo=False)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _set_sqlite_pragma)
    return engine
