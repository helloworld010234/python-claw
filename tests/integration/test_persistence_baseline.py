"""Integration tests for SQLAlchemy repository implementations."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from python_claw.adapters.persistence.repositories import (
    PersistenceError,
    SqlApprovalRepository,
    SqlMessageRepository,
    SqlRunRepository,
    SqlSessionRepository,
)
from python_claw.adapters.persistence.session_factory import create_engine
from python_claw.domain.approval import ApprovalRequest, ApprovalStatus
from python_claw.domain.message import Message, Role, ToolCall, Usage
from python_claw.domain.run import AgentRun, AgentRunStatus
from python_claw.domain.session import Session, SessionStatus

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    """Return a migrated SQLite engine for a single test."""
    db_path = tmp_path / "test.db"
    url = f"sqlite:///{db_path.as_posix()}"
    alembic_cfg = Config(str(ALEMBIC_INI))
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(alembic_cfg, "head")
    return create_engine(url)


@pytest.fixture
def session_repo(engine: Engine) -> SqlSessionRepository:
    return SqlSessionRepository(engine)


@pytest.fixture
def message_repo(engine: Engine) -> SqlMessageRepository:
    return SqlMessageRepository(engine)


@pytest.fixture
def run_repo(engine: Engine) -> SqlRunRepository:
    return SqlRunRepository(engine)


@pytest.fixture
def approval_repo(engine: Engine) -> SqlApprovalRepository:
    return SqlApprovalRepository(engine)


def test_session_save_and_get_by_id(session_repo: SqlSessionRepository) -> None:
    session = Session("sess-1")
    session.append(Message(role=Role.USER, content="hi"))
    session.append(
        Message(
            role=Role.ASSISTANT,
            content="hello",
            usage=Usage(prompt_tokens=5, completion_tokens=3, cost=0.1),
        )
    )
    session.archive()

    session_repo.save(session)
    loaded = session_repo.get_by_id("sess-1")

    assert loaded is not None
    assert loaded.status is SessionStatus.ARCHIVED
    assert loaded.message_count == 2
    assert loaded.total_usage == Usage(prompt_tokens=5, completion_tokens=3, cost=0.1)
    assert [m.role for m in loaded.messages] == [Role.USER, Role.ASSISTANT]
    assert loaded.messages[1].usage == Usage(prompt_tokens=5, completion_tokens=3, cost=0.1)


def test_message_repository_appends_and_lists_in_order(
    session_repo: SqlSessionRepository,
    message_repo: SqlMessageRepository,
) -> None:
    session = Session("sess-2")
    session_repo.save(session)

    message_repo.save(Message(role=Role.USER, content="first"), "sess-2")
    message_repo.save(Message(role=Role.ASSISTANT, content="second"), "sess-2")
    message_repo.save(Message(role=Role.USER, content="third"), "sess-2")

    messages = message_repo.list_by_session("sess-2")
    assert [m.content for m in messages] == ["first", "second", "third"]
    assert [m.role for m in messages] == [Role.USER, Role.ASSISTANT, Role.USER]


def test_message_repository_save_fails_for_missing_session(
    message_repo: SqlMessageRepository,
) -> None:
    with pytest.raises(PersistenceError, match="does not exist"):
        message_repo.save(Message(role=Role.USER, content="orphan"), "no-such-session")


def test_message_repository_appends_usage_updates_session_total_usage(
    session_repo: SqlSessionRepository,
    message_repo: SqlMessageRepository,
) -> None:
    session = Session("sess-usage")
    session_repo.save(session)

    message_repo.save(
        Message(
            role=Role.ASSISTANT,
            content="ok",
            usage=Usage(prompt_tokens=10, completion_tokens=5, cost=0.05),
        ),
        "sess-usage",
    )

    loaded = session_repo.get_by_id("sess-usage")
    assert loaded is not None
    assert loaded.total_usage == Usage(prompt_tokens=10, completion_tokens=5, cost=0.05)


def test_message_repository_appends_multiple_usage_accumulates(
    session_repo: SqlSessionRepository,
    message_repo: SqlMessageRepository,
) -> None:
    session = Session("sess-accum")
    session_repo.save(session)

    message_repo.save(
        Message(role=Role.USER, content="q1"),
        "sess-accum",
    )
    message_repo.save(
        Message(
            role=Role.ASSISTANT,
            content="a1",
            usage=Usage(prompt_tokens=3, completion_tokens=2, cost=0.01),
        ),
        "sess-accum",
    )
    message_repo.save(
        Message(
            role=Role.ASSISTANT,
            content="a2",
            usage=Usage(prompt_tokens=7, completion_tokens=4, cost=0.03),
        ),
        "sess-accum",
    )

    loaded = session_repo.get_by_id("sess-accum")
    assert loaded is not None
    assert loaded.total_usage == Usage(prompt_tokens=10, completion_tokens=6, cost=0.04)


def test_message_repository_appends_without_usage_does_not_change_total(
    session_repo: SqlSessionRepository,
    message_repo: SqlMessageRepository,
) -> None:
    session = Session("sess-no-usage")
    session_repo.save(session)

    message_repo.save(Message(role=Role.USER, content="plain"), "sess-no-usage")

    loaded = session_repo.get_by_id("sess-no-usage")
    assert loaded is not None
    assert loaded.total_usage == Usage()


def test_message_repository_rejects_appending_to_archived_session(
    session_repo: SqlSessionRepository,
    message_repo: SqlMessageRepository,
) -> None:
    session = Session("sess-archived")
    session.append(Message(role=Role.USER, content="before archive"))
    session.archive()
    session_repo.save(session)

    with pytest.raises(PersistenceError, match="is archived"):
        message_repo.save(Message(role=Role.USER, content="after archive"), "sess-archived")

    loaded = session_repo.get_by_id("sess-archived")
    assert loaded is not None
    assert loaded.status is SessionStatus.ARCHIVED
    assert loaded.message_count == 1
    assert loaded.total_usage == Usage()


def test_run_repository_save_fails_for_missing_session(
    run_repo: SqlRunRepository,
) -> None:
    run = AgentRun("run-orphan", "no-such-session", "prompt")
    with pytest.raises(PersistenceError, match="session .no-such-session. does not exist"):
        run_repo.save(run)


def test_approval_repository_save_fails_for_missing_run(
    approval_repo: SqlApprovalRepository,
) -> None:
    approval = ApprovalRequest(
        id="appr-orphan",
        run_id="no-such-run",
        tool_name="bash",
    )
    with pytest.raises(PersistenceError, match="run .no-such-run. does not exist"):
        approval_repo.save(approval)


def test_run_save_and_get_by_id(
    session_repo: SqlSessionRepository,
    run_repo: SqlRunRepository,
) -> None:
    session = Session("sess-run")
    session_repo.save(session)

    run = AgentRun("run-1", "sess-run", "do something")
    run.start()
    run.append_message(Message(role=Role.USER, content="hi"))
    run.append_message(Message(role=Role.ASSISTANT, content="ok"))
    run.complete()

    run_repo.save(run)
    loaded = run_repo.get_by_id("run-1")

    assert loaded is not None
    assert loaded.status is AgentRunStatus.COMPLETED
    assert loaded.prompt == "do something"
    assert loaded.session_id == "sess-run"
    assert [m.role for m in loaded.messages] == [Role.USER, Role.ASSISTANT]


def test_approval_save_and_get_by_id(
    session_repo: SqlSessionRepository,
    run_repo: SqlRunRepository,
    approval_repo: SqlApprovalRepository,
) -> None:
    session = Session("sess-approval")
    session_repo.save(session)

    run = AgentRun("run-approval", "sess-approval", "risky")
    run_repo.save(run)

    approval = ApprovalRequest(
        id="appr-1",
        run_id="run-approval",
        tool_name="bash",
        tool_arguments='{"command": "rm file.txt"}',
    )
    approval_repo.save(approval)

    loaded = approval_repo.get_by_id("appr-1")
    assert loaded is not None
    assert loaded.status is ApprovalStatus.PENDING
    assert loaded.tool_name == "bash"
    assert loaded.tool_arguments == '{"command": "rm file.txt"}'

    approval.approve()
    approval_repo.save(approval)
    loaded = approval_repo.get_by_id("appr-1")
    assert loaded is not None
    assert loaded.status is ApprovalStatus.APPROVED

    approval2 = ApprovalRequest(
        id="appr-2",
        run_id="run-approval",
        tool_name="bash",
    )
    approval2.reject()
    approval_repo.save(approval2)
    loaded2 = approval_repo.get_by_id("appr-2")
    assert loaded2 is not None
    assert loaded2.status is ApprovalStatus.REJECTED

    approval3 = ApprovalRequest(
        id="appr-3",
        run_id="run-approval",
        tool_name="bash",
    )
    approval3.expire()
    approval_repo.save(approval3)
    loaded3 = approval_repo.get_by_id("appr-3")
    assert loaded3 is not None
    assert loaded3.status is ApprovalStatus.EXPIRED


def test_missing_id_returns_none(
    session_repo: SqlSessionRepository,
    run_repo: SqlRunRepository,
    approval_repo: SqlApprovalRepository,
) -> None:
    assert session_repo.get_by_id("missing") is None
    assert run_repo.get_by_id("missing") is None
    assert approval_repo.get_by_id("missing") is None


def test_session_save_is_idempotent(
    session_repo: SqlSessionRepository,
    message_repo: SqlMessageRepository,
) -> None:
    session = Session("sess-dup")
    session.append(Message(role=Role.USER, content="a"))
    session.append(Message(role=Role.ASSISTANT, content="b"))

    session_repo.save(session)
    session_repo.save(session)

    loaded = session_repo.get_by_id("sess-dup")
    assert loaded is not None
    assert loaded.message_count == 2
    assert len(message_repo.list_by_session("sess-dup")) == 2


def test_run_save_is_idempotent(
    session_repo: SqlSessionRepository,
    run_repo: SqlRunRepository,
) -> None:
    session = Session("sess-run-dup")
    session_repo.save(session)

    run = AgentRun("run-dup", "sess-run-dup", "prompt")
    run.append_message(Message(role=Role.USER, content="x"))
    run.append_message(Message(role=Role.ASSISTANT, content="y"))

    run_repo.save(run)
    run_repo.save(run)

    loaded = run_repo.get_by_id("run-dup")
    assert loaded is not None
    assert len(loaded.messages) == 2


def test_tool_calls_json_round_trip(session_repo: SqlSessionRepository) -> None:
    session = Session("sess-tools")
    tool_call = ToolCall(
        id="call-1",
        name="bash",
        arguments={"command": "echo hello", "nested": {"value": 1}},
    )
    session.append(
        Message(
            role=Role.ASSISTANT,
            content="",
            tool_calls=[tool_call],
        )
    )
    session.append(
        Message(
            role=Role.USER,
            content="result",
            tool_call_id="call-1",
        )
    )

    session_repo.save(session)
    loaded = session_repo.get_by_id("sess-tools")

    assert loaded is not None
    assert len(loaded.messages) == 2
    assert loaded.messages[0].tool_calls == (tool_call,)
    assert loaded.messages[0].tool_calls[0].arguments == {
        "command": "echo hello",
        "nested": {"value": 1},
    }
    assert loaded.messages[1].tool_call_id == "call-1"
