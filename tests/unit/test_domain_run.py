from __future__ import annotations

import pytest

from python_claw.domain import AgentRun, AgentRunStatus, Message, PythonClawDomainError, Role


class TestAgentRunCreation:
    def test_requires_non_blank_id(self) -> None:
        with pytest.raises(PythonClawDomainError, match="id"):
            AgentRun(id="", session_id="s-1", prompt="hello")

    def test_requires_non_blank_session_id(self) -> None:
        with pytest.raises(PythonClawDomainError, match="session_id"):
            AgentRun(id="r-1", session_id="", prompt="hello")

    def test_rejects_none_prompt(self) -> None:
        with pytest.raises(PythonClawDomainError, match="prompt"):
            AgentRun(id="r-1", session_id="s-1", prompt=None)  # type: ignore[arg-type]

    def test_defaults_to_pending(self) -> None:
        run = AgentRun(id="r-1", session_id="s-1", prompt="hello")

        assert run.status is AgentRunStatus.PENDING
        assert not run.is_terminal


class TestAgentRunStateTransitions:
    def test_pending_to_running(self) -> None:
        run = AgentRun(id="r-1", session_id="s-1", prompt="hello")

        run.start()

        assert run.status is AgentRunStatus.RUNNING

    def test_running_to_completed(self) -> None:
        run = AgentRun(id="r-1", session_id="s-1", prompt="hello")
        run.start()

        run.complete()

        assert run.status is AgentRunStatus.COMPLETED
        assert run.is_terminal

    def test_running_to_failed(self) -> None:
        run = AgentRun(id="r-1", session_id="s-1", prompt="hello")
        run.start()

        run.fail()

        assert run.status is AgentRunStatus.FAILED

    def test_running_to_cancelled(self) -> None:
        run = AgentRun(id="r-1", session_id="s-1", prompt="hello")
        run.start()

        run.cancel()

        assert run.status is AgentRunStatus.CANCELLED

    def test_running_to_timed_out(self) -> None:
        run = AgentRun(id="r-1", session_id="s-1", prompt="hello")
        run.start()

        run.timeout()

        assert run.status is AgentRunStatus.TIMED_OUT

    def test_pending_cannot_complete(self) -> None:
        run = AgentRun(id="r-1", session_id="s-1", prompt="hello")

        with pytest.raises(PythonClawDomainError, match="Invalid transition"):
            run.complete()

    def test_terminal_cannot_transition(self) -> None:
        run = AgentRun(id="r-1", session_id="s-1", prompt="hello")
        run.start()
        run.fail()

        with pytest.raises(PythonClawDomainError, match="terminal status"):
            run.complete()

    def test_append_message_records_message(self) -> None:
        run = AgentRun(id="r-1", session_id="s-1", prompt="hello")
        message = Message(role=Role.USER, content="hi")

        run.append_message(message)

        assert run.messages == (message,)

    def test_append_non_message_fails(self) -> None:
        run = AgentRun(id="r-1", session_id="s-1", prompt="hello")

        with pytest.raises(PythonClawDomainError, match="Message"):
            run.append_message("not a message")  # type: ignore[arg-type]
