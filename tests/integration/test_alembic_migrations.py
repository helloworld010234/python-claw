"""Integration tests for Alembic migrations."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"

M3_TABLES = {
    "sessions",
    "session_messages",
    "agent_runs",
    "run_messages",
    "approval_requests",
}


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    db_path = tmp_path / "migrations.db"
    return f"sqlite:///{db_path.as_posix()}"


def _collect_table_names(db_url: str) -> set[str]:
    engine = create_engine(db_url)
    with engine.connect() as connection:
        return set(inspect(connection).get_table_names())


def test_alembic_upgrade_head_creates_m3_tables(db_url: str) -> None:
    """An empty SQLite database upgraded to head contains all M3 tables."""
    alembic_cfg = Config(str(ALEMBIC_INI))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_cfg, "head")

    table_names = _collect_table_names(db_url)
    assert M3_TABLES <= table_names
    assert "alembic_version" in table_names


def test_alembic_downgrade_and_reupgrade(db_url: str) -> None:
    """Migrations can be rolled back to base and then upgraded again."""
    alembic_cfg = Config(str(ALEMBIC_INI))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_cfg, "head")
    assert M3_TABLES <= _collect_table_names(db_url)

    command.downgrade(alembic_cfg, "base")
    assert _collect_table_names(db_url).isdisjoint(M3_TABLES)

    command.upgrade(alembic_cfg, "head")
    table_names = _collect_table_names(db_url)
    assert M3_TABLES <= table_names
    assert "alembic_version" in table_names
