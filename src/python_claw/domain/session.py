"""Session aggregate: conversation history, working memory, and usage accounting."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Self

from python_claw.domain.common import PythonClawDomainError
from python_claw.domain.message import Message, Role, Usage


class SessionStatus(StrEnum):
    """Lifecycle states of a session."""

    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass
class Session:
    """Mutable aggregate root holding a conversation.

    State changes are only allowed through ``append`` and ``archive``; internal
    collections are never exposed directly to callers.
    """

    id: str
    _status: SessionStatus = field(default=SessionStatus.ACTIVE, init=False, repr=False)
    _messages: list[Message] = field(default_factory=list, init=False, repr=False)
    _total_usage: Usage = field(default_factory=Usage, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise PythonClawDomainError("Session.id must not be blank")

    @property
    def status(self) -> SessionStatus:
        """Read-only view of the current session status."""
        return self._status

    @property
    def messages(self) -> Sequence[Message]:
        """Read-only view of the full conversation history."""
        return tuple(self._messages)

    @property
    def total_usage(self) -> Usage:
        """Current accumulated usage (immutable value)."""
        return self._total_usage

    @property
    def message_count(self) -> int:
        return len(self._messages)

    @classmethod
    def from_persistence(
        cls,
        session_id: str,
        status: SessionStatus,
        messages: Sequence[Message] | None = None,
        total_usage: Usage | None = None,
    ) -> Self:
        """Reconstruct an aggregate from persisted state without bypassing invariants.

        The provided ``status`` must be a valid ``SessionStatus`` value.
        """
        if not isinstance(status, SessionStatus):
            raise PythonClawDomainError(
                f"Session status must be a SessionStatus, got {type(status)}"
            )
        instance = cls(id=session_id)
        object.__setattr__(instance, "_status", status)
        if messages is not None:
            object.__setattr__(instance, "_messages", list(messages))
        if total_usage is not None:
            object.__setattr__(instance, "_total_usage", total_usage)
        return instance

    def archive(self) -> None:
        """Move the session from ACTIVE to ARCHIVED."""
        self._status = SessionStatus.ARCHIVED

    def append(self, message: Message) -> None:
        """Append a message and accumulate its usage, if present."""
        if self._status is SessionStatus.ARCHIVED:
            raise PythonClawDomainError("Cannot append to an archived session")
        if not isinstance(message, Message):
            raise PythonClawDomainError(f"Session.append requires a Message, got {type(message)}")
        self._messages.append(message)
        if message.usage is not None:
            self._total_usage = self._total_usage.add(message.usage)

    def get_working_memory(self, limit: int) -> Sequence[Message]:
        """Return a window of recent messages with orphaned observations pruned.

        Rules preserved from the Go reference implementation:

        * ``limit <= 0`` or history length not exceeding ``limit``: return a
          full copy of the history.
        * After truncating from the front, repeatedly drop the first retained
          message while it is a user-role tool observation (``tool_call_id`` is
          not ``None``). This avoids starting the window with an isolated tool
          result whose corresponding assistant tool call has been truncated.
        """
        if limit <= 0 or len(self._messages) <= limit:
            return tuple(self._messages)

        window = list(self._messages[-limit:])
        while window:
            first = window[0]
            if first.role is Role.USER and first.tool_call_id is not None:
                window.pop(0)
            else:
                break

        return tuple(window)
