"""Ports for reporting run events and progress."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from python_claw.domain.message import Message
    from python_claw.domain.run import AgentRun


class Reporter(Protocol):
    """Observer for agent-run lifecycle events."""

    def on_run_started(self, run: AgentRun) -> None:
        """Notify that a run has started."""
        ...

    def on_message(self, run: AgentRun, message: Message) -> None:
        """Notify that a new message was produced during a run."""
        ...

    def on_run_finished(self, run: AgentRun) -> None:
        """Notify that a run reached a terminal status."""
        ...
