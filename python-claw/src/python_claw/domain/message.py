"""Core messaging/value objects used by sessions, runs, and LLM interactions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from python_claw.domain.common import PythonClawDomainError


class Role(StrEnum):
    """Participant roles in a conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


def _freeze_json_like(value: Any) -> Any:
    """Recursively convert a JSON-like structure into an immutable equivalent.

    Supports Mapping (including dict and UserDict), list, tuple, set, frozenset,
    str, int, float, bool and None. Mappings are copied into a new plain dict and
    wrapped in ``MappingProxyType`` so callers cannot mutate them through the
    returned mapping view.
    """
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze_json_like(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json_like(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_json_like(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class Usage:
    """Token usage and cost counters."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0

    def __post_init__(self) -> None:
        if self.prompt_tokens < 0:
            raise PythonClawDomainError(
                f"prompt_tokens must be non-negative, got {self.prompt_tokens}"
            )
        if self.completion_tokens < 0:
            raise PythonClawDomainError(
                f"completion_tokens must be non-negative, got {self.completion_tokens}"
            )
        if self.cost < 0:
            raise PythonClawDomainError(f"cost must be non-negative, got {self.cost}")

    def add(self, other: Usage) -> Usage:
        """Return a new Usage with summed counters."""
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            cost=self.cost + other.cost,
        )

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def _coerce_message_list(messages: Sequence[Any], owner_name: str) -> list[Message]:
    """Validate and copy a sequence of messages for aggregate rehydration."""
    result: list[Message] = []
    for index, item in enumerate(messages):
        if not isinstance(item, Message):
            raise PythonClawDomainError(
                f"{owner_name} messages[{index}] must be a Message, got {type(item)}"
            )
        result.append(item)
    return result


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A single tool invocation requested by the assistant."""

    id: str
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise PythonClawDomainError("ToolCall.id must not be blank")
        if not self.name or not self.name.strip():
            raise PythonClawDomainError("ToolCall.name must not be blank")
        if not isinstance(self.arguments, Mapping):
            raise PythonClawDomainError(
                f"ToolCall.arguments must be a mapping, got {type(self.arguments)}"
            )
        object.__setattr__(self, "arguments", _freeze_json_like(self.arguments))


@dataclass(frozen=True, slots=True)
class ToolResult:
    """The outcome of executing a tool call."""

    tool_call_id: str
    output: str = ""
    is_error: bool = False

    def __post_init__(self) -> None:
        if not self.tool_call_id or not self.tool_call_id.strip():
            raise PythonClawDomainError("ToolResult.tool_call_id must not be blank")


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Metadata describing a tool available to the agent."""

    name: str
    description: str
    input_schema: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise PythonClawDomainError("ToolDefinition.name must not be blank")
        if not isinstance(self.input_schema, Mapping):
            raise PythonClawDomainError(
                f"ToolDefinition.input_schema must be a mapping, got {type(self.input_schema)}"
            )
        object.__setattr__(self, "input_schema", _freeze_json_like(self.input_schema))


@dataclass(frozen=True, slots=True)
class Message:
    """A single turn in the conversation.

    Attributes:
        role: The speaker role.
        content: Text payload; for assistant tool calls this may be empty.
        tool_calls: Tool invocations emitted by the assistant.
        tool_call_id: Identifier linking a user-role observation to a prior call.
        usage: Token/cost counters attached to this message, if any.
    """

    role: Role
    content: str = ""
    tool_calls: Sequence[ToolCall] = field(default_factory=tuple)
    tool_call_id: str | None = None
    usage: Usage | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.role, Role):
            raise PythonClawDomainError(f"Message.role must be a Role enum, got {type(self.role)}")

        tool_calls = tuple(self.tool_calls)
        for index, tool_call in enumerate(tool_calls):
            if not isinstance(tool_call, ToolCall):
                raise PythonClawDomainError(
                    f"Message.tool_calls[{index}] must be a ToolCall, got {type(tool_call)}"
                )

        if self.role is Role.ASSISTANT and not self.content and not tool_calls:
            raise PythonClawDomainError("Assistant message must have either content or tool_calls")

        object.__setattr__(self, "tool_calls", tool_calls)
