"""In-memory fakes for unit testing the application layer."""

from __future__ import annotations

from typing import Any

from python_claw.domain.message import Message, Usage
from python_claw.domain.run import AgentRun
from python_claw.domain.session import Session, SessionStatus
from python_claw.ports.repositories import (
    MessageRepository,
    RunRepository,
    SessionRepository,
)
from python_claw.ports.tools import AgentTool, ToolRegistry


class ScriptedLlmGatewayError(Exception):
    """Raised when the scripted LLM gateway runs out of responses."""


class ScriptedLlmGateway:
    """Fake LLM gateway that returns queued responses in order."""

    def __init__(self, responses: list[tuple[Message, Usage]]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.calls: list[list[Message]] = []

    async def chat(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
    ) -> tuple[Message, Usage]:
        self.calls.append(list(messages))
        if self._index >= len(self._responses):
            raise ScriptedLlmGatewayError(
                f"Scripted LLM response queue exhausted at call {self._index}"
            )
        response = self._responses[self._index]
        self._index += 1
        return response


class InMemoryReporter:
    """Records reporter callbacks for assertions."""

    def __init__(self) -> None:
        self.started: list[AgentRun] = []
        self.messages: list[tuple[AgentRun, Message]] = []
        self.finished: list[AgentRun] = []

    def on_run_started(self, run: AgentRun) -> None:
        self.started.append(run)

    def on_message(self, run: AgentRun, message: Message) -> None:
        self.messages.append((run, message))

    def on_run_finished(self, run: AgentRun) -> None:
        self.finished.append(run)


class InMemoryTraceRecorder:
    """Records trace events for assertions."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    def record(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append((run_id, event_type, payload))


class _InMemoryStore:
    """Shared backing store for in-memory repositories."""

    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.runs: dict[str, AgentRun] = {}


class InMemorySessionRepository(SessionRepository):
    """In-memory session aggregate store."""

    def __init__(self, store: _InMemoryStore | None = None) -> None:
        self._store = store or _InMemoryStore()

    def save(self, session: Session) -> None:
        self._store.sessions[session.id] = Session.from_persistence(
            session_id=session.id,
            status=session.status,
            messages=session.messages,
            total_usage=session.total_usage,
        )

    def get_by_id(self, session_id: str) -> Session | None:
        stored = self._store.sessions.get(session_id)
        if stored is None:
            return None
        return Session.from_persistence(
            session_id=stored.id,
            status=stored.status,
            messages=stored.messages,
            total_usage=stored.total_usage,
        )

    @property
    def _backing_store(self) -> _InMemoryStore:
        return self._store


class InMemoryRunRepository(RunRepository):
    """In-memory run aggregate store."""

    def __init__(
        self,
        session_repository: SessionRepository,
        store: _InMemoryStore | None = None,
    ) -> None:
        self._session_repository = session_repository
        self._store = store or _InMemoryStore()

    def save(self, run: AgentRun) -> None:
        if self._session_repository.get_by_id(run.session_id) is None:
            raise RuntimeError(f"Session {run.session_id} does not exist")
        self._store.runs[run.id] = AgentRun.from_persistence(
            run_id=run.id,
            session_id=run.session_id,
            prompt=run.prompt,
            status=run.status,
            messages=run.messages,
        )

    def get_by_id(self, run_id: str) -> AgentRun | None:
        stored = self._store.runs.get(run_id)
        if stored is None:
            return None
        return AgentRun.from_persistence(
            run_id=stored.id,
            session_id=stored.session_id,
            prompt=stored.prompt,
            status=stored.status,
            messages=stored.messages,
        )


class InMemoryMessageRepository(MessageRepository):
    """In-memory session message append store.

    Appends are delegated to the shared session store so that session state remains
    consistent between repositories.
    """

    def __init__(self, session_repository: InMemorySessionRepository) -> None:
        self._session_repository = session_repository

    def save(self, message: Message, session_id: str) -> None:
        session = self._session_repository.get_by_id(session_id)
        if session is None:
            raise RuntimeError(f"Session {session_id} does not exist")
        if session.status is SessionStatus.ARCHIVED:
            raise RuntimeError(f"Session {session_id} is archived")
        session.append(message)
        self._session_repository.save(session)

    def list_by_session(self, session_id: str) -> list[Message]:
        session = self._session_repository.get_by_id(session_id)
        if session is None:
            return []
        return list(session.messages)

    def total_usage_for(self, session_id: str) -> Usage:
        session = self._session_repository.get_by_id(session_id)
        if session is None:
            return Usage()
        return session.total_usage


class InMemoryToolRegistry(ToolRegistry):
    """In-memory tool registry for tests."""

    def __init__(self, tools: list[AgentTool] | None = None) -> None:
        self._tools: dict[str, AgentTool] = {}
        for tool in tools or []:
            self._tools[tool.definition.name] = tool

    def register(self, tool: AgentTool) -> None:
        self._tools[tool.definition.name] = tool

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get(name)

    def list_definitions(self) -> list[Any]:
        return [tool.definition for tool in self._tools.values()]
