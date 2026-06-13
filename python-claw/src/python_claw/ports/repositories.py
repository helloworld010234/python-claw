"""Repository ports for persisting domain aggregates."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from python_claw.domain.approval import ApprovalRequest
    from python_claw.domain.message import Message
    from python_claw.domain.run import AgentRun
    from python_claw.domain.session import Session


class SessionRepository(Protocol):
    """Persistence boundary for ``Session`` aggregates."""

    def save(self, session: Session) -> None:
        """Persist the session."""
        ...

    def get_by_id(self, session_id: str) -> Session | None:
        """Fetch a session by its identifier."""
        ...


class MessageRepository(Protocol):
    """Persistence boundary for ``Message`` entities."""

    def save(self, message: Message, session_id: str) -> None:
        """Persist a message within a session."""
        ...

    def list_by_session(self, session_id: str) -> list[Message]:
        """Return all messages for a session in chronological order."""
        ...


class RunRepository(Protocol):
    """Persistence boundary for ``AgentRun`` aggregates."""

    def save(self, run: AgentRun) -> None:
        """Persist the run."""
        ...

    def get_by_id(self, run_id: str) -> AgentRun | None:
        """Fetch a run by its identifier."""
        ...


class ApprovalRepository(Protocol):
    """Persistence boundary for ``ApprovalRequest`` aggregates."""

    def save(self, approval: ApprovalRequest) -> None:
        """Persist the approval request."""
        ...

    def get_by_id(self, approval_id: str) -> ApprovalRequest | None:
        """Fetch an approval request by its identifier."""
        ...
