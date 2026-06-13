"""Approval request aggregate for dangerous tool operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Self

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
    _status: ApprovalStatus = field(default=ApprovalStatus.PENDING, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise PythonClawDomainError("ApprovalRequest.id must not be blank")
        if not self.run_id or not self.run_id.strip():
            raise PythonClawDomainError("ApprovalRequest.run_id must not be blank")
        if not self.tool_name or not self.tool_name.strip():
            raise PythonClawDomainError("ApprovalRequest.tool_name must not be blank")

    @property
    def status(self) -> ApprovalStatus:
        """Read-only view of the current approval status."""
        return self._status

    @property
    def is_terminal(self) -> bool:
        return self._status in _TERMINAL_STATUSES

    @classmethod
    def from_persistence(
        cls,
        approval_id: str,
        run_id: str,
        tool_name: str,
        status: ApprovalStatus,
        tool_arguments: str = "",
    ) -> Self:
        """Reconstruct an aggregate from persisted state without bypassing invariants.

        The provided ``status`` must be a valid ``ApprovalStatus`` value.
        """
        if not isinstance(status, ApprovalStatus):
            raise PythonClawDomainError(
                f"ApprovalRequest status must be an ApprovalStatus, got {type(status)}"
            )
        instance = cls(
            id=approval_id,
            run_id=run_id,
            tool_name=tool_name,
            tool_arguments=tool_arguments,
        )
        object.__setattr__(instance, "_status", status)
        return instance

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
        if self._status in _TERMINAL_STATUSES:
            raise PythonClawDomainError(
                "Cannot transition from terminal status "
                f"{self._status.value} to {next_status.value}"
            )
        if self._status is ApprovalStatus.PENDING and next_status in _TERMINAL_STATUSES:
            self._status = next_status
            return
        raise PythonClawDomainError(
            f"Invalid transition from {self._status.value} to {next_status.value}"
        )
