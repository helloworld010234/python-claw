"""AgentRun aggregate: lifecycle state machine for a single agent execution."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Self

from python_claw.domain.common import PythonClawDomainError
from python_claw.domain.message import Message


class AgentRunStatus(StrEnum):
    """AgentRun lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


_TERMINAL_STATUSES: frozenset[AgentRunStatus] = frozenset(
    {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
        AgentRunStatus.TIMED_OUT,
    }
)

_VALID_TRANSITIONS: dict[AgentRunStatus, frozenset[AgentRunStatus]] = {
    AgentRunStatus.PENDING: frozenset({AgentRunStatus.RUNNING}),
    AgentRunStatus.RUNNING: frozenset(
        {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
            AgentRunStatus.TIMED_OUT,
        }
    ),
}


@dataclass
class AgentRun:
    """Mutable aggregate root tracking a single execution request."""

    id: str
    session_id: str
    prompt: str
    _status: AgentRunStatus = field(default=AgentRunStatus.PENDING, init=False, repr=False)
    _messages: list[Message] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise PythonClawDomainError("AgentRun.id must not be blank")
        if not self.session_id or not self.session_id.strip():
            raise PythonClawDomainError("AgentRun.session_id must not be blank")
        if self.prompt is None:
            raise PythonClawDomainError("AgentRun.prompt must not be None")

    @property
    def status(self) -> AgentRunStatus:
        """Read-only view of the current lifecycle status."""
        return self._status

    @property
    def messages(self) -> Sequence[Message]:
        """Read-only view of messages produced during the run."""
        return tuple(self._messages)

    @property
    def is_terminal(self) -> bool:
        return self._status in _TERMINAL_STATUSES

    @classmethod
    def from_persistence(
        cls,
        run_id: str,
        session_id: str,
        prompt: str,
        status: AgentRunStatus,
        messages: Sequence[Message] | None = None,
    ) -> Self:
        """Reconstruct an aggregate from persisted state without bypassing invariants.

        The provided ``status`` must be a valid ``AgentRunStatus`` value.
        """
        if not isinstance(status, AgentRunStatus):
            raise PythonClawDomainError(
                f"AgentRun status must be an AgentRunStatus, got {type(status)}"
            )
        instance = cls(id=run_id, session_id=session_id, prompt=prompt)
        object.__setattr__(instance, "_status", status)
        if messages is not None:
            object.__setattr__(instance, "_messages", list(messages))
        return instance

    def start(self) -> None:
        """Move the run from PENDING to RUNNING."""
        self._transition_to(AgentRunStatus.RUNNING)

    def complete(self) -> None:
        """Move the run from RUNNING to COMPLETED."""
        self._transition_to(AgentRunStatus.COMPLETED)

    def fail(self) -> None:
        """Move the run from RUNNING to FAILED."""
        self._transition_to(AgentRunStatus.FAILED)

    def cancel(self) -> None:
        """Move the run from RUNNING to CANCELLED."""
        self._transition_to(AgentRunStatus.CANCELLED)

    def timeout(self) -> None:
        """Move the run from RUNNING to TIMED_OUT."""
        self._transition_to(AgentRunStatus.TIMED_OUT)

    def append_message(self, message: Message) -> None:
        """Record a message produced during the run."""
        if not isinstance(message, Message):
            raise PythonClawDomainError(
                f"AgentRun.append_message requires a Message, got {type(message)}"
            )
        self._messages.append(message)

    def _transition_to(self, next_status: AgentRunStatus) -> None:
        if self._status in _TERMINAL_STATUSES:
            raise PythonClawDomainError(
                "Cannot transition from terminal status "
                f"{self._status.value} to {next_status.value}"
            )

        allowed = _VALID_TRANSITIONS.get(self._status)
        if allowed is None or next_status not in allowed:
            raise PythonClawDomainError(
                f"Invalid transition from {self._status.value} to {next_status.value}"
            )

        self._status = next_status
