"""Approval request aggregate for dangerous tool operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from python_claw.domain.common import PythonClawDomainError


class ApprovalStatus(StrEnum):
    """Lifecycle states of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


_TERMINAL_STATUSES: frozenset[ApprovalStatus] = frozenset(
    {
        ApprovalStatus.APPROVED,
        ApprovalStatus.REJECTED,
        ApprovalStatus.EXPIRED,
    }
)


@dataclass
class ApprovalRequest:
    """Mutable aggregate root representing a human-in-the-loop approval."""

    id: str
    run_id: str
    tool_name: str
    tool_arguments: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise PythonClawDomainError("ApprovalRequest.id must not be blank")
        if not self.run_id or not self.run_id.strip():
            raise PythonClawDomainError("ApprovalRequest.run_id must not be blank")
        if not self.tool_name or not self.tool_name.strip():
            raise PythonClawDomainError("ApprovalRequest.tool_name must not be blank")

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_STATUSES

    def approve(self) -> None:
        """Approve the request."""
        self._transition_to(ApprovalStatus.APPROVED)

    def reject(self) -> None:
        """Reject the request."""
        self._transition_to(ApprovalStatus.REJECTED)

    def expire(self) -> None:
        """Mark the request as expired."""
        self._transition_to(ApprovalStatus.EXPIRED)

    def _transition_to(self, next_status: ApprovalStatus) -> None:
        if self.status in _TERMINAL_STATUSES:
            raise PythonClawDomainError(
                f"Cannot transition from terminal status {self.status.value} to {next_status.value}"
            )
        if self.status is ApprovalStatus.PENDING and next_status in _TERMINAL_STATUSES:
            self.status = next_status
            return
        raise PythonClawDomainError(
            f"Invalid transition from {self.status.value} to {next_status.value}"
        )
