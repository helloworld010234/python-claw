from __future__ import annotations

from collections.abc import Mapping

import pytest

from python_claw.domain import (
    Message,
    PythonClawDomainError,
    Role,
    ToolCall,
    ToolDefinition,
    ToolResult,
    Usage,
)


class TestUsage:
    def test_add_sums_counters(self) -> None:
        first = Usage(prompt_tokens=3, completion_tokens=2, cost=0.1)
        second = Usage(prompt_tokens=7, completion_tokens=5, cost=0.2)

        total = first.add(second)

        assert total.prompt_tokens == 10
        assert total.completion_tokens == 7
        assert total.cost == pytest.approx(0.3)
        assert total.total_tokens == 17

    def test_rejects_negative_tokens(self) -> None:
        with pytest.raises(PythonClawDomainError, match="prompt_tokens"):
            Usage(prompt_tokens=-1)

    def test_rejects_negative_cost(self) -> None:
        with pytest.raises(PythonClawDomainError, match="cost"):
            Usage(cost=-0.01)


class TestToolCall:
    def test_requires_non_blank_id(self) -> None:
        with pytest.raises(PythonClawDomainError, match="id"):
            ToolCall(id="", name="read_file")

    def test_requires_non_blank_name(self) -> None:
        with pytest.raises(PythonClawDomainError, match="name"):
            ToolCall(id="call-1", name="")

    def test_arguments_default_is_empty_mapping(self) -> None:
        call = ToolCall(id="call-1", name="read_file")

        assert isinstance(call.arguments, Mapping)
        assert dict(call.arguments) == {}

    def test_arguments_not_shared_between_instances(self) -> None:
        call_one = ToolCall(id="call-1", name="read_file")
        call_two = ToolCall(id="call-2", name="read_file")

        assert call_one.arguments is not call_two.arguments

    def test_arguments_are_copied_from_external_dict(self) -> None:
        external = {"path": "README.md"}
        call = ToolCall(id="call-1", name="read_file", arguments=external)

        external["path"] = "mutated"

        assert dict(call.arguments) == {"path": "README.md"}

    def test_arguments_are_immutable(self) -> None:
        call = ToolCall(id="call-1", name="read_file", arguments={"path": "README.md"})

        with pytest.raises(TypeError):
            call.arguments["path"] = "mutated"  # type: ignore[index]

    def test_nested_arguments_are_frozen(self) -> None:
        external = {
            "items": [{"name": "a"}, {"name": "b"}],
            "tags": {"important"},
            "nested": {"value": 1},
        }
        call = ToolCall(id="call-1", name="complex", arguments=external)

        external["items"][0]["name"] = "mutated"
        external["nested"]["value"] = 99
        external["tags"].add("ignored")

        assert call.arguments["items"] == ({"name": "a"}, {"name": "b"})
        assert call.arguments["nested"]["value"] == 1
        assert call.arguments["tags"] == frozenset({"important"})
        with pytest.raises(TypeError):
            call.arguments["items"][0]["name"] = "mutated"  # type: ignore[index]

    def test_arguments_must_be_mapping(self) -> None:
        with pytest.raises(PythonClawDomainError, match="mapping"):
            ToolCall(id="call-1", name="read_file", arguments=["not", "a", "mapping"])  # type: ignore[arg-type]


class TestToolResult:
    def test_requires_non_blank_tool_call_id(self) -> None:
        with pytest.raises(PythonClawDomainError, match="tool_call_id"):
            ToolResult(tool_call_id="", output="ok")


class TestToolDefinition:
    def test_requires_non_blank_name(self) -> None:
        with pytest.raises(PythonClawDomainError, match="name"):
            ToolDefinition(name="", description="reads a file")

    def test_input_schema_is_copied_from_external_dict(self) -> None:
        external = {"type": "object", "properties": {"path": {"type": "string"}}}
        definition = ToolDefinition(
            name="read_file", description="reads a file", input_schema=external
        )

        external["properties"]["path"]["type"] = "mutated"

        assert definition.input_schema["properties"]["path"]["type"] == "string"

    def test_input_schema_is_immutable(self) -> None:
        definition = ToolDefinition(
            name="read_file",
            description="reads a file",
            input_schema={"type": "object"},
        )

        with pytest.raises(TypeError):
            definition.input_schema["type"] = "array"  # type: ignore[index]


class TestMessage:
    def test_assistant_message_must_have_content_or_tool_calls(self) -> None:
        with pytest.raises(PythonClawDomainError, match="content or tool_calls"):
            Message(role=Role.ASSISTANT)

    def test_assistant_message_with_tool_calls_is_valid(self) -> None:
        call = ToolCall(id="call-1", name="read_file")
        message = Message(role=Role.ASSISTANT, tool_calls=(call,))

        assert message.role is Role.ASSISTANT
        assert message.tool_calls == (call,)

    def test_assistant_message_accepts_tool_calls_as_list(self) -> None:
        call = ToolCall(id="call-1", name="read_file")
        message = Message(role=Role.ASSISTANT, tool_calls=[call])

        assert isinstance(message.tool_calls, tuple)
        assert message.tool_calls == (call,)

    def test_tool_calls_default_is_empty_tuple(self) -> None:
        message = Message(role=Role.USER, content="hello")

        assert message.tool_calls == ()

    def test_tool_calls_list_append_does_not_affect_message(self) -> None:
        call = ToolCall(id="call-1", name="read_file")
        calls = [call]
        message = Message(role=Role.ASSISTANT, tool_calls=calls)

        calls.append(ToolCall(id="call-2", name="write_file"))

        assert len(message.tool_calls) == 1
        assert message.tool_calls[0].id == "call-1"

    def test_rejects_tool_calls_with_non_tool_call_elements(self) -> None:
        with pytest.raises(PythonClawDomainError, match="ToolCall"):
            Message(role=Role.ASSISTANT, tool_calls=["not-a-tool-call"])  # type: ignore[list-item]

    def test_message_is_immutable(self) -> None:
        message = Message(role=Role.USER, content="hello")

        with pytest.raises(AttributeError):
            message.content = "goodbye"  # type: ignore[misc]

    def test_rejects_invalid_role_type(self) -> None:
        with pytest.raises(PythonClawDomainError, match="Role enum"):
            Message(role="user", content="hello")  # type: ignore[arg-type]
