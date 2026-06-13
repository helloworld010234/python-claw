"""Unit tests for the mockable agent engine."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from python_claw.application import (
    AgentEngine,
    AgentEngineConfig,
    AgentEngineError,
    RunAgentCommand,
)
from python_claw.domain.message import (
    Message,
    Role,
    ToolCall,
    ToolDefinition,
    ToolResult,
    Usage,
)
from python_claw.domain.run import AgentRunStatus
from python_claw.domain.session import Session
from python_claw.ports.tools import AgentTool
from tests.unit.fakes import (
    InMemoryMessageRepository,
    InMemoryReporter,
    InMemoryRunRepository,
    InMemorySessionRepository,
    InMemoryToolRegistry,
    InMemoryTraceRecorder,
    ScriptedLlmGateway,
)


class ExplodingReporter(InMemoryReporter):
    """Reporter fake that can fail on selected lifecycle callbacks."""

    def __init__(
        self,
        *,
        fail_started: bool = False,
        fail_message: bool = False,
        fail_finished: bool = False,
    ) -> None:
        super().__init__()
        self._fail_started = fail_started
        self._fail_message = fail_message
        self._fail_finished = fail_finished

    def on_run_started(self, run) -> None:  # type: ignore[no-untyped-def]
        if self._fail_started:
            raise RuntimeError("reporter start down")
        super().on_run_started(run)

    def on_message(self, run, message) -> None:  # type: ignore[no-untyped-def]
        if self._fail_message:
            raise RuntimeError("reporter message down")
        super().on_message(run, message)

    def on_run_finished(self, run) -> None:  # type: ignore[no-untyped-def]
        if self._fail_finished:
            raise RuntimeError("reporter finish down")
        super().on_run_finished(run)


class ExplodingTraceRecorder(InMemoryTraceRecorder):
    """Trace recorder fake that can fail for selected event types."""

    def __init__(self, failing_event_types: set[str]) -> None:
        super().__init__()
        self._failing_event_types = failing_event_types

    def record(self, run_id: str, event_type: str, payload: dict) -> None:  # type: ignore[type-arg]
        if event_type in self._failing_event_types:
            raise RuntimeError(f"trace {event_type} down")
        super().record(run_id, event_type, payload)


@dataclass
class EchoTool(AgentTool):
    """Fake tool that echoes the value argument."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="echo",
            description="Echo the provided value.",
            input_schema={"type": "object"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        value = call.arguments.get("value", "")
        return ToolResult(tool_call_id=call.id, output=str(value))


@dataclass
class ErrorTool(AgentTool):
    """Fake tool that always returns an error."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="error_tool",
            description="Always fails.",
            input_schema={"type": "object"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult(
            tool_call_id=call.id,
            output="boom",
            is_error=True,
        )


@pytest.fixture
def session_repository() -> InMemorySessionRepository:
    return InMemorySessionRepository()


@pytest.fixture
def run_repository(
    session_repository: InMemorySessionRepository,
) -> InMemoryRunRepository:
    return InMemoryRunRepository(
        session_repository, store=session_repository._backing_store
    )


@pytest.fixture
def message_repository(
    session_repository: InMemorySessionRepository,
) -> InMemoryMessageRepository:
    return InMemoryMessageRepository(session_repository)


@pytest.fixture
def reporter() -> InMemoryReporter:
    return InMemoryReporter()


@pytest.fixture
def trace_recorder() -> InMemoryTraceRecorder:
    return InMemoryTraceRecorder()


@pytest.fixture
def tool_registry() -> InMemoryToolRegistry:
    return InMemoryToolRegistry([EchoTool(), ErrorTool()])


@pytest.fixture
def engine(
    session_repository: InMemorySessionRepository,
    run_repository: InMemoryRunRepository,
    message_repository: InMemoryMessageRepository,
    tool_registry: InMemoryToolRegistry,
    reporter: InMemoryReporter,
    trace_recorder: InMemoryTraceRecorder,
) -> AgentEngine:
    return AgentEngine(
        session_repository=session_repository,
        run_repository=run_repository,
        message_repository=message_repository,
        llm_gateway=ScriptedLlmGateway([]),
        tool_registry=tool_registry,
        reporter=reporter,
        trace_recorder=trace_recorder,
        config=AgentEngineConfig(max_turns=20, working_memory_limit=20),
    )


async def test_run_completes_without_tool_calls(
    engine: AgentEngine,
    session_repository: InMemorySessionRepository,
    run_repository: InMemoryRunRepository,
) -> None:
    engine._llm_gateway = ScriptedLlmGateway(
        [(Message(role=Role.ASSISTANT, content="hello"), Usage())]
    )

    run = await engine.run(
        RunAgentCommand(
            run_id="run-1",
            session_id="session-1",
            prompt="hi",
        )
    )

    assert run.status is AgentRunStatus.COMPLETED
    assert len(run.messages) == 2
    assert run.messages[0].role is Role.USER
    assert run.messages[1].role is Role.ASSISTANT
    assert run.messages[1].content == "hello"

    session = session_repository.get_by_id("session-1")
    assert session is not None
    assert len(session.messages) == 2
    assert session.messages[0].role is Role.USER
    assert session.messages[1].role is Role.ASSISTANT

    persisted_run = run_repository.get_by_id("run-1")
    assert persisted_run is not None
    assert persisted_run.status is AgentRunStatus.COMPLETED


async def test_run_with_single_tool_call(
    engine: AgentEngine,
    session_repository: InMemorySessionRepository,
    run_repository: InMemoryRunRepository,
    trace_recorder: InMemoryTraceRecorder,
) -> None:
    engine._llm_gateway = ScriptedLlmGateway(
        [
            (
                Message(
                    role=Role.ASSISTANT,
                    content="",
                    tool_calls=[
                        ToolCall(id="call-1", name="echo", arguments={"value": "hi"})
                    ],
                ),
                Usage(prompt_tokens=3, completion_tokens=2),
            ),
            (Message(role=Role.ASSISTANT, content="done"), Usage(prompt_tokens=1)),
        ]
    )

    run = await engine.run(
        RunAgentCommand(run_id="run-1", session_id="session-1", prompt="call echo")
    )

    assert run.status is AgentRunStatus.COMPLETED
    assert len(run.messages) == 4
    assert run.messages[2].role is Role.USER
    assert run.messages[2].tool_call_id == "call-1"
    assert run.messages[2].content == "hi"
    assert run.messages[3].role is Role.ASSISTANT
    assert run.messages[3].content == "done"

    session = session_repository.get_by_id("session-1")
    assert session is not None
    assert len(session.messages) == 4
    assert session.messages[2].tool_call_id == "call-1"

    persisted_run = run_repository.get_by_id("run-1")
    assert persisted_run is not None
    assert len(persisted_run.messages) == 4

    event_types = [event_type for _rid, event_type, _payload in trace_recorder.events]
    assert event_types == [
        "run_started",
        "llm_response",
        "tool_result",
        "llm_response",
        "run_finished",
    ]


async def test_unknown_tool_writes_error_observation(
    engine: AgentEngine,
    session_repository: InMemorySessionRepository,
) -> None:
    engine._llm_gateway = ScriptedLlmGateway(
        [
            (
                Message(
                    role=Role.ASSISTANT,
                    content="",
                    tool_calls=[ToolCall(id="call-1", name="missing_tool")],
                ),
                Usage(),
            ),
            (Message(role=Role.ASSISTANT, content="done"), Usage()),
        ]
    )

    run = await engine.run(
        RunAgentCommand(run_id="run-1", session_id="session-1", prompt="call missing")
    )

    assert run.status is AgentRunStatus.COMPLETED
    assert len(run.messages) == 4
    observation = run.messages[2]
    assert observation.role is Role.USER
    assert observation.tool_call_id == "call-1"
    assert "missing_tool" in observation.content
    assert "not found" in observation.content

    session = session_repository.get_by_id("session-1")
    assert session is not None
    assert len(session.messages) == 4


async def test_tool_error_observation_is_written(
    engine: AgentEngine,
    session_repository: InMemorySessionRepository,
) -> None:
    engine._llm_gateway = ScriptedLlmGateway(
        [
            (
                Message(
                    role=Role.ASSISTANT,
                    content="",
                    tool_calls=[ToolCall(id="call-1", name="error_tool")],
                ),
                Usage(),
            ),
            (Message(role=Role.ASSISTANT, content="done"), Usage()),
        ]
    )

    run = await engine.run(
        RunAgentCommand(run_id="run-1", session_id="session-1", prompt="call error")
    )

    assert run.status is AgentRunStatus.COMPLETED
    observation = run.messages[2]
    assert observation.role is Role.USER
    assert observation.tool_call_id == "call-1"
    assert observation.content == "boom"

    session = session_repository.get_by_id("session-1")
    assert session is not None
    assert session.messages[2].content == "boom"


async def test_max_turns_exhausted_marks_run_timed_out(
    engine: AgentEngine,
    run_repository: InMemoryRunRepository,
) -> None:
    engine._config = AgentEngineConfig(max_turns=2, working_memory_limit=20)
    engine._llm_gateway = ScriptedLlmGateway(
        [
            (
                Message(
                    role=Role.ASSISTANT,
                    content="",
                    tool_calls=[ToolCall(id=f"call-{i}", name="echo")],
                ),
                Usage(),
            )
            for i in range(3)
        ]
    )

    run = await engine.run(
        RunAgentCommand(run_id="run-1", session_id="session-1", prompt="loop")
    )

    assert run.status is AgentRunStatus.TIMED_OUT
    assert len(run.messages) == 1 + 2 * 2  # user + 2 assistant/tool pairs

    persisted_run = run_repository.get_by_id("run-1")
    assert persisted_run is not None
    assert persisted_run.status is AgentRunStatus.TIMED_OUT


async def test_archived_session_rejects_run(
    engine: AgentEngine,
    session_repository: InMemorySessionRepository,
    message_repository: InMemoryMessageRepository,
    reporter: InMemoryReporter,
) -> None:
    session = Session(id="session-1")
    session.archive()
    session_repository.save(session)

    with pytest.raises(AgentEngineError):
        await engine.run(
            RunAgentCommand(run_id="run-1", session_id="session-1", prompt="hi")
        )

    assert len(reporter.started) == 0
    assert len(reporter.messages) == 0
    assert len(reporter.finished) == 0
    assert message_repository.list_by_session("session-1") == []


async def test_llm_exception_marks_run_failed(
    engine: AgentEngine,
    run_repository: InMemoryRunRepository,
) -> None:
    class ExplodingLlmGateway(ScriptedLlmGateway):
        async def chat(self, messages: list[Message], tools: list | None = None):
            self.calls.append(list(messages))
            raise RuntimeError("llm down")

    engine._llm_gateway = ExplodingLlmGateway([])

    with pytest.raises(AgentEngineError):
        await engine.run(
            RunAgentCommand(run_id="run-1", session_id="session-1", prompt="hi")
        )

    persisted_run = run_repository.get_by_id("run-1")
    assert persisted_run is not None
    assert persisted_run.status is AgentRunStatus.FAILED


async def test_usage_accumulates_in_session_total_usage(
    engine: AgentEngine,
    session_repository: InMemorySessionRepository,
) -> None:
    engine._llm_gateway = ScriptedLlmGateway(
        [(Message(role=Role.ASSISTANT, content="hello"), Usage(2, 1, 0.5))]
    )

    await engine.run(
        RunAgentCommand(run_id="run-1", session_id="session-1", prompt="hi")
    )

    session = session_repository.get_by_id("session-1")
    assert session is not None
    assert session.total_usage.prompt_tokens == 2
    assert session.total_usage.completion_tokens == 1
    assert session.total_usage.cost == pytest.approx(0.5)


async def test_reporter_receives_started_message_finished(
    engine: AgentEngine,
    reporter: InMemoryReporter,
) -> None:
    engine._llm_gateway = ScriptedLlmGateway(
        [(Message(role=Role.ASSISTANT, content="hello"), Usage())]
    )

    await engine.run(
        RunAgentCommand(run_id="run-1", session_id="session-1", prompt="hi")
    )

    assert len(reporter.started) == 1
    assert reporter.started[0].id == "run-1"
    assert len(reporter.messages) == 1
    assert reporter.messages[0][1].role is Role.ASSISTANT
    assert len(reporter.finished) == 1
    assert reporter.finished[0].id == "run-1"
    assert reporter.finished[0].status is AgentRunStatus.COMPLETED


async def test_trace_records_key_events(
    engine: AgentEngine,
    trace_recorder: InMemoryTraceRecorder,
) -> None:
    engine._llm_gateway = ScriptedLlmGateway(
        [
            (
                Message(
                    role=Role.ASSISTANT,
                    content="",
                    tool_calls=[ToolCall(id="call-1", name="echo", arguments={"value": "x"})],
                ),
                Usage(),
            ),
            (Message(role=Role.ASSISTANT, content="done"), Usage()),
        ]
    )

    await engine.run(
        RunAgentCommand(run_id="run-1", session_id="session-1", prompt="trace me")
    )

    event_types = [event_type for _rid, event_type, _payload in trace_recorder.events]
    assert "run_started" in event_types
    assert "llm_response" in event_types
    assert "tool_result" in event_types
    assert "run_finished" in event_types


async def test_start_reporter_failure_does_not_leave_run_running(
    session_repository: InMemorySessionRepository,
    run_repository: InMemoryRunRepository,
    message_repository: InMemoryMessageRepository,
    tool_registry: InMemoryToolRegistry,
    trace_recorder: InMemoryTraceRecorder,
) -> None:
    engine = AgentEngine(
        session_repository=session_repository,
        run_repository=run_repository,
        message_repository=message_repository,
        llm_gateway=ScriptedLlmGateway(
            [(Message(role=Role.ASSISTANT, content="hello"), Usage())]
        ),
        tool_registry=tool_registry,
        reporter=ExplodingReporter(fail_started=True),
        trace_recorder=trace_recorder,
        config=AgentEngineConfig(),
    )

    run = await engine.run(
        RunAgentCommand(run_id="run-1", session_id="session-1", prompt="hi")
    )

    assert run.status is AgentRunStatus.COMPLETED
    persisted_run = run_repository.get_by_id("run-1")
    assert persisted_run is not None
    assert persisted_run.status is AgentRunStatus.COMPLETED


async def test_start_trace_failure_does_not_leave_run_running(
    session_repository: InMemorySessionRepository,
    run_repository: InMemoryRunRepository,
    message_repository: InMemoryMessageRepository,
    tool_registry: InMemoryToolRegistry,
    reporter: InMemoryReporter,
) -> None:
    engine = AgentEngine(
        session_repository=session_repository,
        run_repository=run_repository,
        message_repository=message_repository,
        llm_gateway=ScriptedLlmGateway(
            [(Message(role=Role.ASSISTANT, content="hello"), Usage())]
        ),
        tool_registry=tool_registry,
        reporter=reporter,
        trace_recorder=ExplodingTraceRecorder({"run_started"}),
        config=AgentEngineConfig(),
    )

    run = await engine.run(
        RunAgentCommand(run_id="run-1", session_id="session-1", prompt="hi")
    )

    assert run.status is AgentRunStatus.COMPLETED
    persisted_run = run_repository.get_by_id("run-1")
    assert persisted_run is not None
    assert persisted_run.status is AgentRunStatus.COMPLETED


async def test_finish_reporter_failure_does_not_break_completed_run(
    session_repository: InMemorySessionRepository,
    run_repository: InMemoryRunRepository,
    message_repository: InMemoryMessageRepository,
    tool_registry: InMemoryToolRegistry,
    trace_recorder: InMemoryTraceRecorder,
) -> None:
    engine = AgentEngine(
        session_repository=session_repository,
        run_repository=run_repository,
        message_repository=message_repository,
        llm_gateway=ScriptedLlmGateway(
            [(Message(role=Role.ASSISTANT, content="hello"), Usage())]
        ),
        tool_registry=tool_registry,
        reporter=ExplodingReporter(fail_finished=True),
        trace_recorder=trace_recorder,
        config=AgentEngineConfig(),
    )

    run = await engine.run(
        RunAgentCommand(run_id="run-1", session_id="session-1", prompt="hi")
    )

    assert run.status is AgentRunStatus.COMPLETED
    persisted_run = run_repository.get_by_id("run-1")
    assert persisted_run is not None
    assert persisted_run.status is AgentRunStatus.COMPLETED


async def test_failure_observer_errors_do_not_mask_agent_engine_error(
    session_repository: InMemorySessionRepository,
    run_repository: InMemoryRunRepository,
    message_repository: InMemoryMessageRepository,
    tool_registry: InMemoryToolRegistry,
) -> None:
    class ExplodingLlmGateway(ScriptedLlmGateway):
        async def chat(self, messages: list[Message], tools: list | None = None):
            self.calls.append(list(messages))
            raise RuntimeError("llm down")

    engine = AgentEngine(
        session_repository=session_repository,
        run_repository=run_repository,
        message_repository=message_repository,
        llm_gateway=ExplodingLlmGateway([]),
        tool_registry=tool_registry,
        reporter=ExplodingReporter(fail_finished=True),
        trace_recorder=ExplodingTraceRecorder({"run_finished"}),
        config=AgentEngineConfig(),
    )

    with pytest.raises(AgentEngineError, match="llm down"):
        await engine.run(
            RunAgentCommand(run_id="run-1", session_id="session-1", prompt="hi")
        )

    persisted_run = run_repository.get_by_id("run-1")
    assert persisted_run is not None
    assert persisted_run.status is AgentRunStatus.FAILED


async def test_existing_session_is_reused(
    engine: AgentEngine,
    session_repository: InMemorySessionRepository,
    message_repository: InMemoryMessageRepository,
) -> None:
    session = Session(id="session-1")
    session.append(Message(role=Role.USER, content="previous"))
    session_repository.save(session)

    engine._llm_gateway = ScriptedLlmGateway(
        [(Message(role=Role.ASSISTANT, content="hello"), Usage())]
    )

    run = await engine.run(
        RunAgentCommand(run_id="run-1", session_id="session-1", prompt="hi")
    )

    assert run.status is AgentRunStatus.COMPLETED
    session = session_repository.get_by_id("session-1")
    assert session is not None
    assert len(session.messages) == 3  # previous + new prompt + assistant
    assert message_repository.list_by_session("session-1") == list(session.messages)
