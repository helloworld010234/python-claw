"""Integration tests for SQLAlchemy + Alembic persistence adapters.

Tests use a temporary SQLite database created by Alembic migrations so no
external PostgreSQL server or persistent database files are required.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from python_claw.adapters.persistence.database import get_engine
from python_claw.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlMessageRepository,
    SqlRunRepository,
    SqlSessionRepository,
)
from python_claw.domain.approval import ApprovalRequest, ApprovalStatus
from python_claw.domain.common import PythonClawDomainError
from python_claw.domain.message import Message, Role, ToolCall, Usage
from python_claw.domain.run import AgentRun, AgentRunStatus
from python_claw.domain.session import Session, SessionStatus

if TYPE_CHECKING:
    from sqlalchemy import Engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_TABLES = {
    "agent_sessions",
    "agent_messages",
    "agent_runs",
    "approval_requests",
}


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    """Return a fresh SQLite URL for each test."""
    db_path = tmp_path / "test.db"
    return f"sqlite:///{db_path}"


@pytest.fixture
def engine(sqlite_url: str) -> Engine:
    """Create an engine and apply Alembic migrations."""
    test_engine = get_engine(sqlite_url)
    alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", sqlite_url)
    command.upgrade(alembic_cfg, "head")
    return test_engine


@pytest.fixture
def repositories(engine: Engine) -> dict[str, object]:
    """Return initialized SQLAlchemy repository adapters."""
    return {
        "session": SqlSessionRepository(engine),
        "message": SqlMessageRepository(engine),
        "run": SqlRunRepository(engine),
        "approval": SqlApprovalRepository(engine),
    }


def test_alembic_upgrade_creates_required_tables(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert REQUIRED_TABLES <= tables


def test_session_save_and_get_roundtrip(repositories: dict[str, object]) -> None:
    session_repo = repositories["session"]
    session = Session(id="sess-1")
    session.append(Message(role=Role.USER, content="hello"))
    session.append(
        Message(
            role=Role.ASSISTANT,
            content="hi there",
            usage=Usage(prompt_tokens=10, completion_tokens=5, cost=0.001),
        )
    )
    session.archive()

    session_repo.save(session)
    loaded = session_repo.get_by_id("sess-1")

    assert loaded is not None
    assert loaded.id == "sess-1"
    assert loaded.status is SessionStatus.ARCHIVED
    assert loaded.message_count == 2
    assert loaded.total_usage == Usage(prompt_tokens=10, completion_tokens=5, cost=0.001)
    assert [message.role for message in loaded.messages] == [Role.USER, Role.ASSISTANT]
    assert loaded.messages[1].content == "hi there"


def test_session_update_does_not_duplicate_records(
    repositories: dict[str, object], engine: Engine
) -> None:
    session_repo = repositories["session"]
    session = Session(id="sess-dup")
    session.append(Message(role=Role.USER, content="first"))
    session_repo.save(session)

    session.append(Message(role=Role.ASSISTANT, content="second"))
    session_repo.save(session)

    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT COUNT(*) FROM agent_sessions WHERE id = :id"),
            {"id": "sess-dup"},
        ).scalar()
        message_count = connection.execute(
            text("SELECT COUNT(*) FROM agent_messages WHERE session_id = :id AND run_id IS NULL"),
            {"id": "sess-dup"},
        ).scalar()

    assert count == 1
    assert message_count == 2

    loaded = session_repo.get_by_id("sess-dup")
    assert loaded is not None
    assert loaded.message_count == 2
    assert loaded.messages[1].content == "second"


def test_message_save_and_list_roundtrip(repositories: dict[str, object]) -> None:
    session_repo = repositories["session"]
    message_repo = repositories["message"]

    session = Session(id="sess-msg")
    session_repo.save(session)

    tool_call = ToolCall(
        id="tc-1",
        name="read_file",
        arguments={"path": "test.txt"},
    )
    message_repo.save(
        Message(
            role=Role.ASSISTANT,
            content="",
            tool_calls=[tool_call],
            usage=Usage(prompt_tokens=7, completion_tokens=3, cost=0.0005),
        ),
        session_id="sess-msg",
    )
    message_repo.save(
        Message(role=Role.USER, content="result content", tool_call_id="tc-1"),
        session_id="sess-msg",
    )

    messages = message_repo.list_by_session("sess-msg")
    assert len(messages) == 2
    assert messages[0].role is Role.ASSISTANT
    assert messages[0].tool_calls == (tool_call,)
    assert messages[0].usage == Usage(prompt_tokens=7, completion_tokens=3, cost=0.0005)
    assert messages[1].role is Role.USER
    assert messages[1].tool_call_id == "tc-1"


def test_run_save_and_get_roundtrip(repositories: dict[str, object]) -> None:
    session_repo = repositories["session"]
    run_repo = repositories["run"]

    session = Session(id="sess-run")
    session_repo.save(session)

    run = AgentRun(id="run-1", session_id="sess-run", prompt="do work")
    run.start()
    run.append_message(Message(role=Role.USER, content=run.prompt))
    run.append_message(
        Message(
            role=Role.ASSISTANT,
            content="done",
            usage=Usage(prompt_tokens=5, completion_tokens=4, cost=0.0003),
        )
    )
    run.complete()
    run_repo.save(run)

    loaded = run_repo.get_by_id("run-1")
    assert loaded is not None
    assert loaded.id == "run-1"
    assert loaded.session_id == "sess-run"
    assert loaded.status is AgentRunStatus.COMPLETED
    assert loaded.prompt == "do work"
    assert loaded.is_terminal is True
    assert len(loaded.messages) == 2
    assert loaded.messages[0].role is Role.USER
    assert loaded.messages[1].role is Role.ASSISTANT
    assert loaded.messages[1].usage == Usage(prompt_tokens=5, completion_tokens=4, cost=0.0003)


def test_approval_save_and_get_roundtrip(repositories: dict[str, object]) -> None:
    session_repo = repositories["session"]
    run_repo = repositories["run"]
    approval_repo = repositories["approval"]

    session = Session(id="sess-approval")
    session_repo.save(session)
    run = AgentRun(id="run-approval", session_id="sess-approval", prompt="dangerous task")
    run_repo.save(run)

    approval = ApprovalRequest(
        id="app-1",
        run_id="run-approval",
        tool_name="bash",
        tool_arguments='{"command": "ls -la"}',
    )
    approval.approve()
    approval_repo.save(approval)

    loaded = approval_repo.get_by_id("app-1")
    assert loaded is not None
    assert loaded.id == "app-1"
    assert loaded.run_id == "run-approval"
    assert loaded.tool_name == "bash"
    assert loaded.tool_arguments == '{"command": "ls -la"}'
    assert loaded.status is ApprovalStatus.APPROVED
    assert loaded.is_terminal is True


def test_update_same_id_does_not_duplicate_approval(
    repositories: dict[str, object], engine: Engine
) -> None:
    session_repo = repositories["session"]
    run_repo = repositories["run"]
    approval_repo = repositories["approval"]

    session = Session(id="sess-approval-update")
    session_repo.save(session)
    run = AgentRun(id="run-approval-update", session_id="sess-approval-update", prompt="task")
    run_repo.save(run)

    approval = ApprovalRequest(
        id="app-update",
        run_id="run-approval-update",
        tool_name="bash",
        tool_arguments="old args",
    )
    approval_repo.save(approval)
    approval.approve()
    approval_repo.save(approval)

    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT COUNT(*) FROM approval_requests WHERE id = :id"),
            {"id": "app-update"},
        ).scalar()

    assert count == 1

    loaded = approval_repo.get_by_id("app-update")
    assert loaded is not None
    assert loaded.status is ApprovalStatus.APPROVED
    assert loaded.tool_arguments == "old args"


def test_invalid_session_status_rehydrate_raises(
    repositories: dict[str, object],
    engine: Engine,
) -> None:
    session_repo = repositories["session"]
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO agent_sessions "
                "(id, status, total_prompt_tokens, total_completion_tokens, "
                "total_cost, created_at, updated_at) "
                "VALUES (:id, :status, 0, 0, 0.0, :now, :now)"
            ),
            {
                "id": "bad-sess",
                "status": "not_a_status",
                "now": "2026-01-01 00:00:00",
            },
        )

    with pytest.raises(PythonClawDomainError):
        session_repo.get_by_id("bad-sess")


def test_session_messages_with_immutable_arguments_roundtrip(
    repositories: dict[str, object],
) -> None:
    session_repo = repositories["session"]
    session = Session(id="sess-immutable")
    tool_call = ToolCall(
        id="tc-immutable",
        name="edit_file",
        arguments={"path": "a.txt", "options": {"mode": "append"}},
    )
    session.append(
        Message(
            role=Role.ASSISTANT,
            content="",
            tool_calls=[tool_call],
        )
    )
    session_repo.save(session)

    loaded = session_repo.get_by_id("sess-immutable")
    assert loaded is not None
    assert len(loaded.messages) == 1
    loaded_tool_call = loaded.messages[0].tool_calls[0]
    assert loaded_tool_call.id == "tc-immutable"
    assert loaded_tool_call.name == "edit_file"
    assert dict(loaded_tool_call.arguments) == {
        "path": "a.txt",
        "options": {"mode": "append"},
    }


def test_session_and_run_messages_are_isolated(
    repositories: dict[str, object], engine: Engine
) -> None:
    """Session-level messages must never be polluted by run-level messages."""
    session_repo = repositories["session"]
    message_repo = repositories["message"]
    run_repo = repositories["run"]

    session = Session(id="sess-isolated")
    session.append(Message(role=Role.USER, content="session-level"))
    session_repo.save(session)

    message_repo.save(
        Message(role=Role.ASSISTANT, content="also session-level"),
        session_id="sess-isolated",
    )

    run = AgentRun(id="run-isolated", session_id="sess-isolated", prompt="do work")
    run.start()
    run.append_message(Message(role=Role.USER, content="run-level"))
    run.append_message(Message(role=Role.ASSISTANT, content="run-done"))
    run.complete()
    run_repo.save(run)

    loaded_session = session_repo.get_by_id("sess-isolated")
    assert loaded_session is not None
    assert [message.content for message in loaded_session.messages] == [
        "session-level",
        "also session-level",
    ]

    listed_messages = message_repo.list_by_session("sess-isolated")
    assert [message.content for message in listed_messages] == [
        "session-level",
        "also session-level",
    ]

    loaded_run = run_repo.get_by_id("run-isolated")
    assert loaded_run is not None
    assert [message.content for message in loaded_run.messages] == [
        "run-level",
        "run-done",
    ]

    with engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    "SELECT run_id, content FROM agent_messages "
                    "WHERE session_id = :session_id ORDER BY ordinal"
                ),
                {"session_id": "sess-isolated"},
            )
            .mappings()
            .all()
        )

    session_rows = [row for row in rows if row["run_id"] is None]
    run_rows = [row for row in rows if row["run_id"] == "run-isolated"]
    assert len(session_rows) == 2
    assert len(run_rows) == 2


def test_sqlite_foreign_keys_enabled(engine: Engine) -> None:
    """SQLite connections produced by get_engine must enforce foreign keys."""
    with engine.connect() as connection:
        result = connection.execute(text("PRAGMA foreign_keys")).scalar()
    assert result == 1


def test_sqlite_foreign_key_rejects_orphan_run(
    repositories: dict[str, object], engine: Engine
) -> None:
    """Saving a run referencing a missing session must fail and leave no record."""
    run_repo = repositories["run"]
    run = AgentRun(id="run-orphan", session_id="missing-session", prompt="x")

    with pytest.raises(IntegrityError):
        run_repo.save(run)

    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT COUNT(*) FROM agent_runs WHERE id = :id"),
            {"id": "run-orphan"},
        ).scalar()
    assert count == 0


def test_sqlite_foreign_key_rejects_orphan_approval(
    repositories: dict[str, object], engine: Engine
) -> None:
    """Saving an approval referencing a missing run must fail and leave no record."""
    approval_repo = repositories["approval"]
    approval = ApprovalRequest(id="app-orphan", run_id="missing-run", tool_name="bash")

    with pytest.raises(IntegrityError):
        approval_repo.save(approval)

    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT COUNT(*) FROM approval_requests WHERE id = :id"),
            {"id": "app-orphan"},
        ).scalar()
    assert count == 0


def test_agent_messages_indexes_exist(engine: Engine) -> None:
    """The message table must carry the expected lookup indexes."""
    inspector = inspect(engine)
    indexes = {index["name"] for index in inspector.get_indexes("agent_messages")}
    assert "ix_agent_messages_session_run_ordinal" in indexes
    assert "ix_agent_messages_run_ordinal" in indexes
