"""JSON serialization helpers for domain value objects."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from python_claw.domain.message import Message, Role, ToolCall, Usage


def _unfreeze_json_like(value: Any) -> Any:
    """Recursively convert immutable JSON-like structures into plain Python objects.

    ``MappingProxyType`` becomes ``dict``, ``tuple`` becomes ``list``, and
    ``frozenset`` becomes ``list`` so that the result is JSON-serializable.
    """
    if isinstance(value, Mapping):
        return {k: _unfreeze_json_like(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_unfreeze_json_like(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_unfreeze_json_like(item) for item in value]
    return value


def _tool_call_to_dict(tool_call: ToolCall) -> dict[str, Any]:
    """Convert a ``ToolCall`` to a plain dictionary."""
    return {
        "id": tool_call.id,
        "name": tool_call.name,
        "arguments": _unfreeze_json_like(tool_call.arguments),
    }


def _tool_call_from_dict(data: dict[str, Any] | ToolCall) -> ToolCall:
    """Reconstruct a ``ToolCall`` from a plain dictionary or pass-through an existing one."""
    if isinstance(data, ToolCall):
        return data
    return ToolCall(
        id=data["id"],
        name=data["name"],
        arguments=data.get("arguments", {}),
    )


def tool_calls_to_json(tool_calls: Sequence[ToolCall]) -> str:
    """Serialize a sequence of ``ToolCall`` objects to a JSON string."""
    payload = [_tool_call_to_dict(tc) for tc in tool_calls]
    return json.dumps(payload, ensure_ascii=False)


def tool_calls_from_json(raw: str) -> tuple[ToolCall, ...]:
    """Deserialize a JSON string into a tuple of ``ToolCall`` objects."""
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("tool_calls_json must be a JSON array")
    return tuple(_tool_call_from_dict(item) for item in parsed)


def message_to_dict(message: Message) -> dict[str, Any]:
    """Convert a ``Message`` into a JSON-serializable dictionary."""
    usage = message.usage
    return {
        "role": message.role.value,
        "content": message.content,
        "tool_calls": [_tool_call_to_dict(tc) for tc in message.tool_calls],
        "tool_call_id": message.tool_call_id,
        "usage": (
            {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "cost": usage.cost,
            }
            if usage is not None
            else None
        ),
    }


def message_from_dict(data: dict[str, Any]) -> Message:
    """Reconstruct a ``Message`` from a plain dictionary."""
    usage_data = data.get("usage")
    usage: Usage | None = None
    if usage_data is not None:
        usage = Usage(
            prompt_tokens=int(usage_data["prompt_tokens"]),
            completion_tokens=int(usage_data["completion_tokens"]),
            cost=float(usage_data["cost"]),
        )

    tool_call_id = data.get("tool_call_id")
    if tool_call_id == "":
        tool_call_id = None

    tool_calls_raw = data.get("tool_calls") or []
    tool_calls = [_tool_call_from_dict(item) for item in tool_calls_raw]

    return Message(
        role=Role(data["role"]),
        content=data.get("content", ""),
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        usage=usage,
    )
