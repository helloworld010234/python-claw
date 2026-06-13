from __future__ import annotations

import pytest

from python_claw.domain import (
    Message,
    PythonClawDomainError,
    Role,
    Session,
    SessionStatus,
    ToolCall,
    Usage,
)


class TestSessionCreation:
    def test_requires_non_blank_id(self) -> None:
        with pytest.raises(PythonClawDomainError, match="id"):
            Session(id="")

    def test_defaults_to_active(self) -> None:
        session = Session(id="s-1")

        assert session.status is SessionStatus.ACTIVE


class TestSessionAppend:
    def test_appends_message_and_accumulates_usage(self) -> None:
        session = Session(id="s-1")
        message = Message(role=Role.USER, content="hello", usage=Usage(prompt_tokens=2))

        session.append(message)

        assert session.message_count == 1
        assert session.total_usage.prompt_tokens == 2

    def test_appending_non_message_fails(self) -> None:
        session = Session(id="s-1")

        with pytest.raises(PythonClawDomainError, match="Message"):
            session.append("not a message")  # type: ignore[arg-type]

    def test_messages_returns_immutable_copy(self) -> None:
        session = Session(id="s-1")
        session.append(Message(role=Role.USER, content="hello"))

        view = session.messages
        with pytest.raises(TypeError):
            view[0] = Message(role=Role.USER, content=" mutated")  # type: ignore[index]


class TestSessionWorkingMemory:
    def test_limit_zero_returns_full_history(self) -> None:
        session = Session(id="s-1")
        for i in range(3):
            session.append(Message(role=Role.USER, content=f"msg-{i}"))

        assert session.get_working_memory(0) == session.messages

    def test_limit_exceeding_history_returns_full_copy(self) -> None:
        session = Session(id="s-1")
        session.append(Message(role=Role.USER, content="msg-1"))

        window = session.get_working_memory(10)

        assert len(window) == 1
        assert window is not session.messages

    def test_truncates_to_last_n_messages(self) -> None:
        session = Session(id="s-1")
        for i in range(5):
            session.append(Message(role=Role.USER, content=f"msg-{i}"))

        window = session.get_working_memory(3)

        assert [m.content for m in window] == ["msg-2", "msg-3", "msg-4"]

    def test_prunes_isolated_tool_observation(self) -> None:
        session = Session(id="s-1")
        session.append(Message(role=Role.USER, content="start"))
        session.append(Message(role=Role.USER, content="obs-1", tool_call_id="call-1"))
        session.append(Message(role=Role.USER, content="obs-2", tool_call_id="call-2"))
        session.append(
            Message(
                role=Role.ASSISTANT,
                tool_calls=(ToolCall(id="call-2", name="read_file"),),
            )
        )

        window = session.get_working_memory(3)

        assert len(window) == 2
        assert window[0].content == "obs-2"
        assert window[0].tool_call_id == "call-2"
        assert window[1].role is Role.ASSISTANT

    def test_keeps_non_isolated_first_observation(self) -> None:
        session = Session(id="s-1")
        session.append(Message(role=Role.USER, content="start"))
        session.append(
            Message(
                role=Role.ASSISTANT,
                tool_calls=(
                    ToolCall(id="call-1", name="read_file"),
                    ToolCall(id="call-2", name="read_file"),
                ),
            )
        )
        session.append(Message(role=Role.USER, content="obs-1", tool_call_id="call-1"))
        session.append(Message(role=Role.USER, content="obs-2", tool_call_id="call-2"))

        window = session.get_working_memory(3)

        assert len(window) == 3
        assert window[0].role is Role.ASSISTANT
        assert window[1].tool_call_id == "call-1"
        assert window[2].tool_call_id == "call-2"

    def test_window_result_is_immutable(self) -> None:
        session = Session(id="s-1")
        for i in range(3):
            session.append(Message(role=Role.USER, content=f"msg-{i}"))

        window = session.get_working_memory(2)

        with pytest.raises(TypeError):
            window[0] = Message(role=Role.USER, content="mutated")  # type: ignore[index]
