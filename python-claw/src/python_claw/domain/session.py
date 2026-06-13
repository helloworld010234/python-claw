"""Session aggregate: conversation history, working memory, and usage accounting."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from python_claw.domain.common import PythonClawDomainError
from python_claw.domain.message import Message, Usage


class SessionStatus(StrEnum):
    """Lifecycle states of a session."""

    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass
class Session:
    """Mutable aggregate root holding a conversation.

    State changes are only allowed through ``append``; internal collections are
    never exposed directly to callers.
    """

    id: str
    status: SessionStatus = SessionStatus.ACTIVE
    _messages: list[Message] = field(default_factory=list, init=False, repr=False)
    _total_usage: Usage = field(default_factory=Usage, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise PythonClawDomainError("Session.id must not be blank")

    @property
    def messages(self) -> Sequence[Message]:
        """Read-only view of the full conversation history."""
        return tuple(self._messages)

    @property
    def total_usage(self) -> Usage:
        """Current accumulated usage; returned as a copy."""
        return self._total_usage

    @property
    def message_count(self) -> int:
        return len(self._messages)

    def append(self, message: Message) -> None:
        """Append a message and accumulate its usage, if present."""
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
        * After truncating from the front, if the first retained message is a
          user-role tool observation whose ``tool_call_id`` no longer appears in
          any retained assistant ``tool_calls``, drop it as an isolated result.
          Repeat until the first message is not an isolated tool result.
        """
        if limit <= 0 or len(self._messages) <= limit:
            return tuple(self._messages)

        window = list(self._messages[-limit:])
        assistant_call_ids = {
            tool_call.id
            for message in window
            if message.role.value == "assistant"
            for tool_call in message.tool_calls
        }

        while window:
            first = window[0]
            if first.role.value != "user" or first.tool_call_id is None:
                break
            if first.tool_call_id in assistant_call_ids:
                break
            window.pop(0)

        return tuple(window)
