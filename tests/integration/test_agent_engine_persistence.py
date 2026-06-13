"""Integration tests for AgentEngine with SQLAlchemy persistence."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from python_claw.adapters.persistence.repositories import (
    SqlMessageRepository,
    SqlRunRepository,
    SqlSessionRepository,
)
from python_claw.adapters.persistence.session_factory import create_engine
from python_claw.application import AgentEngine, AgentEngineConfig, RunAgentCommand
from python_claw.domain.message import Message, Role, Usage
from python_claw.domain.run import AgentRunStatus
from tests.unit.fakes import (
    InMemoryReporter,
    InMemoryToolRegistry,
    InMemoryTraceRecorder,
    ScriptedLlmGateway,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    """Return a migrated SQLite engine for a single AgentEngine test."""
    db_path = tmp_path / "agent_engine.db"
    url = f"sqlite:///{db_path.as_posix()}"
    alembic_cfg = Config(str(ALEMBIC_INI))
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(alembic_cfg, "head")
    return create_engine(url)


async def test_agent_engine_persists_completed_run_with_sql_repositories(
    engine: Engine,
) -> None:
    """AgentEngine can complete a run using the real SQL repository adapters."""
    session_repo = SqlSessionRepository(engine)
    run_repo = SqlRunRepository(engine)
    message_repo = SqlMessageRepository(engine)
    reporter = InMemoryReporter()
    trace_recorder = InMemoryTraceRecorder()
    agent = AgentEngine(
        session_repository=session_repo,
        run_repository=run_repo,
        message_repository=message_repo,
        llm_gateway=ScriptedLlmGateway(
            [
                (
                    Message(role=Role.ASSISTANT, content="sql-ok"),
                    Usage(prompt_tokens=2, completion_tokens=1, cost=0.25),
                )
            ]
        ),
        tool_registry=InMemoryToolRegistry(),
        reporter=reporter,
        trace_recorder=trace_recorder,
        config=AgentEngineConfig(max_turns=3, working_memory_limit=5),
    )

    run = await agent.run(
        RunAgentCommand(run_id="run-sql", session_id="session-sql", prompt="hello")
    )

    persisted_run = run_repo.get_by_id("run-sql")
    persisted_session = session_repo.get_by_id("session-sql")
    assert run.status is AgentRunStatus.COMPLETED
    assert persisted_run is not None
    assert persisted_run.status is AgentRunStatus.COMPLETED
    assert [message.content for message in persisted_run.messages] == ["hello", "sql-ok"]
    assert persisted_session is not None
    assert [message.content for message in persisted_session.messages] == [
        "hello",
        "sql-ok",
    ]
    assert persisted_session.total_usage == Usage(
        prompt_tokens=2,
        completion_tokens=1,
        cost=0.25,
    )
    assert len(reporter.started) == 1
    assert len(reporter.messages) == 1
    assert len(reporter.finished) == 1
    assert [event_type for _run_id, event_type, _payload in trace_recorder.events] == [
        "run_started",
        "llm_response",
        "run_finished",
    ]
