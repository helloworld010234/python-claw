"""Domain object serialization helpers for the SQLAlchemy persistence adapter.

All JSON stored in SQLite ``Text`` columns is converted to plain Python
collections before ``json.dumps`` so immutable domain values such as
``MappingProxyType``, ``tuple`` and ``frozenset`` round-trip correctly.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from python_claw.adapters.persistence.models import (
    AgentMessageModel,
    AgentRunModel,
    AgentSessionModel,
    ApprovalRequestModel,
)
from python_claw.domain.approval import ApprovalRequest, ApprovalStatus
from python_claw.domain.common import PythonClawDomainError
from python_claw.domain.message import Message, Role, ToolCall, Usage
from python_claw.domain.run import AgentRun, AgentRunStatus
from python_claw.domain.session import Session, SessionStatus


def now_utc() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


def _json_compatible(value: Any) -> Any:
    """Recursively convert immutable JSON-like values into plain JSON-serializable objects."""
    if isinstance(value, MappingProxyType):
        return {k: _json_compatible(v) for k, v in value.items()}
    if isinstance(value, Mapping):
        return {k: _json_compatible(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_json_compatible(item) for item in value]
    return value


def _to_json(value: Any) -> str:
    """Serialize a JSON-compatible value to a string."""
    return json.dumps(_json_compatible(value), ensure_ascii=False)


def _parse_enum[E: StrEnum](enum_cls: type[E], value: str, field_name: str) -> E:
    """Parse a persisted enum value, raising a domain error when invalid."""
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise PythonClawDomainError(f"Invalid persisted {field_name}: {value!r}") from exc


def usage_to_json(usage: Usage) -> str:
    """Serialize ``Usage`` to JSON."""
    return _to_json(
        {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "cost": usage.cost,
        }
    )


def usage_from_json(raw: str) -> Usage:
    """Deserialize ``Usage`` from JSON."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise PythonClawDomainError(f"Invalid usage JSON: expected object, got {type(data)}")
    return Usage(
        prompt_tokens=int(data.get("prompt_tokens", 0)),
        completion_tokens=int(data.get("completion_tokens", 0)),
        cost=float(data.get("cost", 0.0)),
    )


def tool_calls_to_json(tool_calls: Sequence[ToolCall]) -> str:
    """Serialize a sequence of ``ToolCall`` objects to JSON."""
    payload = [
        {
            "id": tool_call.id,
            "name": tool_call.name,
            "arguments": tool_call.arguments,
        }
        for tool_call in tool_calls
    ]
    return _to_json(payload)


def tool_calls_from_json(raw: str) -> tuple[ToolCall, ...]:
    """Deserialize ``ToolCall`` objects from JSON."""
    data = json.loads(raw)
    if data is None:
        return ()
    if not isinstance(data, list):
        raise PythonClawDomainError(f"Invalid tool_calls JSON: expected list, got {type(data)}")
    result: list[ToolCall] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise PythonClawDomainError(
                f"Invalid tool_calls JSON at index {index}: expected object, got {type(item)}"
            )
        result.append(
            ToolCall(
                id=str(item.get("id", "")),
                name=str(item.get("name", "")),
                arguments=item.get("arguments", {}),
            )
        )
    return tuple(result)


def message_to_model(
    message: Message,
    *,
    ordinal: int,
    session_id: str | None = None,
    run_id: str | None = None,
) -> AgentMessageModel:
    """Convert a domain ``Message`` into a persistence model."""
    usage_json = usage_to_json(message.usage) if message.usage is not None else "null"
    return AgentMessageModel(
        session_id=session_id,
        run_id=run_id,
        ordinal=ordinal,
        role=message.role.value,
        content=message.content,
        tool_calls_json=tool_calls_to_json(message.tool_calls),
        tool_call_id=message.tool_call_id,
        usage_json=usage_json,
        created_at=now_utc(),
    )


def message_from_model(model: AgentMessageModel) -> Message:
    """Convert a persistence message model into a domain ``Message``."""
    usage = None
    if model.usage_json and model.usage_json != "null":
        usage = usage_from_json(model.usage_json)
    return Message(
        role=Role(model.role),
        content=model.content,
        tool_calls=tool_calls_from_json(model.tool_calls_json),
        tool_call_id=model.tool_call_id,
        usage=usage,
    )


def session_to_model(session: Session) -> AgentSessionModel:
    """Convert a domain ``Session`` aggregate into a persistence model."""
    now = now_utc()
    model = AgentSessionModel(
        id=session.id,
        status=session.status.value,
        total_prompt_tokens=session.total_usage.prompt_tokens,
        total_completion_tokens=session.total_usage.completion_tokens,
        total_cost=session.total_usage.cost,
        created_at=now,
        updated_at=now,
    )
    model.messages = [
        message_to_model(message, ordinal=index, session_id=session.id)
        for index, message in enumerate(session.messages)
    ]
    return model


def session_from_model(model: AgentSessionModel) -> Session:
    """Convert a persistence session model into a domain ``Session``."""
    messages = sorted(
        (message for message in model.messages if message.run_id is None),
        key=lambda message: message.ordinal,
    )
    total_usage = Usage(
        prompt_tokens=model.total_prompt_tokens,
        completion_tokens=model.total_completion_tokens,
        cost=model.total_cost,
    )
    return Session.from_persistence(
        session_id=model.id,
        status=_parse_enum(SessionStatus, model.status, "Session.status"),
        messages=[message_from_model(message) for message in messages],
        total_usage=total_usage,
    )


def run_to_model(run: AgentRun) -> AgentRunModel:
    """Convert a domain ``AgentRun`` aggregate into a persistence model."""
    now = now_utc()
    model = AgentRunModel(
        id=run.id,
        session_id=run.session_id,
        prompt=run.prompt,
        status=run.status.value,
        created_at=now,
        updated_at=now,
    )
    model.messages = [
        message_to_model(
            message,
            ordinal=index,
            run_id=run.id,
            session_id=run.session_id,
        )
        for index, message in enumerate(run.messages)
    ]
    return model


def run_from_model(model: AgentRunModel) -> AgentRun:
    """Convert a persistence run model into a domain ``AgentRun``."""
    messages = sorted(model.messages, key=lambda message: message.ordinal)
    return AgentRun.from_persistence(
        run_id=model.id,
        session_id=model.session_id,
        prompt=model.prompt,
        status=_parse_enum(AgentRunStatus, model.status, "AgentRun.status"),
        messages=[message_from_model(message) for message in messages],
    )


def approval_to_model(approval: ApprovalRequest) -> ApprovalRequestModel:
    """Convert a domain ``ApprovalRequest`` into a persistence model."""
    now = now_utc()
    return ApprovalRequestModel(
        id=approval.id,
        run_id=approval.run_id,
        tool_name=approval.tool_name,
        tool_arguments=approval.tool_arguments,
        status=approval.status.value,
        created_at=now,
        updated_at=now,
    )


def approval_from_model(model: ApprovalRequestModel) -> ApprovalRequest:
    """Convert a persistence approval model into a domain ``ApprovalRequest``."""
    return ApprovalRequest.from_persistence(
        approval_id=model.id,
        run_id=model.run_id,
        tool_name=model.tool_name,
        status=_parse_enum(ApprovalStatus, model.status, "ApprovalRequest.status"),
        tool_arguments=model.tool_arguments,
    )
