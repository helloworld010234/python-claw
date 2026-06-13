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

    def test_status_cannot_be_set_directly(self) -> None:
        session = Session(id="s-1")

        with pytest.raises(AttributeError):
            session.status = SessionStatus.ARCHIVED  # type: ignore[misc]


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

    def test_appending_to_archived_session_fails(self) -> None:
        session = Session(id="s-1")
        session.archive()

        with pytest.raises(PythonClawDomainError, match="archived"):
            session.append(Message(role=Role.USER, content="hello"))

    def test_messages_returns_immutable_copy(self) -> None:
        session = Session(id="s-1")
        session.append(Message(role=Role.USER, content="hello"))

        view = session.messages
        with pytest.raises(TypeError):
            view[0] = Message(role=Role.USER, content=" mutated")  # type: ignore[index]


class TestSessionArchive:
    def test_archive_moves_session_to_archived(self) -> None:
        session = Session(id="s-1")

        session.archive()

        assert session.status is SessionStatus.ARCHIVED


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

    def test_prunes_leading_user_tool_observations_after_truncation(self) -> None:
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

        assert len(window) == 1
        assert window[0].role is Role.ASSISTANT

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


class TestSessionPersistenceFactory:
    def test_reconstructs_aggregate_with_status_and_messages(self) -> None:
        message = Message(role=Role.USER, content="hello")
        session = Session.from_persistence(
            session_id="s-1",
            status=SessionStatus.ARCHIVED,
            messages=[message],
            total_usage=Usage(prompt_tokens=2),
        )

        assert session.status is SessionStatus.ARCHIVED
        assert session.messages == (message,)
        assert session.total_usage.prompt_tokens == 2

    def test_factory_rejects_non_enum_status(self) -> None:
        with pytest.raises(PythonClawDomainError, match="SessionStatus"):
            Session.from_persistence(
                session_id="s-1",
                status="archived",  # type: ignore[arg-type]
            )

    def test_factory_rejects_messages_with_non_message_elements(self) -> None:
        with pytest.raises(PythonClawDomainError, match="messages\\[0\\].*Message"):
            Session.from_persistence(
                session_id="s-1",
                status=SessionStatus.ACTIVE,
                messages=["bad"],  # type: ignore[list-item]
            )

    def test_factory_rejects_non_usage_total_usage(self) -> None:
        with pytest.raises(PythonClawDomainError, match="total_usage.*Usage"):
            Session.from_persistence(
                session_id="s-1",
                status=SessionStatus.ACTIVE,
                total_usage="bad",  # type: ignore[arg-type]
            )

    def test_factory_does_not_retain_external_messages_list(self) -> None:
        message = Message(role=Role.USER, content="hello")
        external_messages = [message]
        session = Session.from_persistence(
            session_id="s-1",
            status=SessionStatus.ACTIVE,
            messages=external_messages,
        )

        external_messages.append(Message(role=Role.USER, content="extra"))

        assert session.message_count == 1
        assert session.messages == (message,)
