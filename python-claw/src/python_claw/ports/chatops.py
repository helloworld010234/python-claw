"""Port for ChatOps integrations (e.g., Feishu/Lark)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from python_claw.domain.approval import ApprovalRequest
    from python_claw.domain.run import AgentRun


class ChatOpsPort(Protocol):
    """Abstraction over an enterprise chat platform used for approvals and notifications."""

    async def request_approval(self, request: ApprovalRequest) -> None:
        """Send an approval request to the chat platform."""
        ...

    async def notify_run_finished(self, run: AgentRun) -> None:
        """Notify a channel or user that a run has finished."""
        ...
