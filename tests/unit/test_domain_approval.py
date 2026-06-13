from __future__ import annotations

import pytest

from python_claw.domain import ApprovalRequest, ApprovalStatus, PythonClawDomainError


class TestApprovalRequestCreation:
    def test_requires_non_blank_id(self) -> None:
        with pytest.raises(PythonClawDomainError, match="id"):
            ApprovalRequest(id="", run_id="r-1", tool_name="bash")

    def test_requires_non_blank_run_id(self) -> None:
        with pytest.raises(PythonClawDomainError, match="run_id"):
            ApprovalRequest(id="a-1", run_id="", tool_name="bash")

    def test_requires_non_blank_tool_name(self) -> None:
        with pytest.raises(PythonClawDomainError, match="tool_name"):
            ApprovalRequest(id="a-1", run_id="r-1", tool_name="")

    def test_defaults_to_pending(self) -> None:
        request = ApprovalRequest(id="a-1", run_id="r-1", tool_name="bash")

        assert request.status is ApprovalStatus.PENDING
        assert not request.is_terminal

    def test_status_cannot_be_set_directly(self) -> None:
        request = ApprovalRequest(id="a-1", run_id="r-1", tool_name="bash")

        with pytest.raises(AttributeError):
            request.status = ApprovalStatus.APPROVED  # type: ignore[misc]


class TestApprovalLifecycle:
    def test_pending_to_approved(self) -> None:
        request = ApprovalRequest(id="a-1", run_id="r-1", tool_name="bash")

        request.approve()

        assert request.status is ApprovalStatus.APPROVED
        assert request.is_terminal

    def test_pending_to_rejected(self) -> None:
        request = ApprovalRequest(id="a-1", run_id="r-1", tool_name="bash")

        request.reject()

        assert request.status is ApprovalStatus.REJECTED

    def test_pending_to_expired(self) -> None:
        request = ApprovalRequest(id="a-1", run_id="r-1", tool_name="bash")

        request.expire()

        assert request.status is ApprovalStatus.EXPIRED

    def test_terminal_cannot_transition(self) -> None:
        request = ApprovalRequest(id="a-1", run_id="r-1", tool_name="bash")
        request.reject()

        with pytest.raises(PythonClawDomainError, match="terminal status"):
            request.approve()


class TestApprovalPersistenceFactory:
    def test_reconstructs_aggregate_with_status(self) -> None:
        request = ApprovalRequest.from_persistence(
            approval_id="a-1",
            run_id="r-1",
            tool_name="bash",
            status=ApprovalStatus.APPROVED,
        )

        assert request.status is ApprovalStatus.APPROVED
        assert request.is_terminal

    def test_factory_rejects_non_enum_status(self) -> None:
        with pytest.raises(PythonClawDomainError, match="ApprovalStatus"):
            ApprovalRequest.from_persistence(
                approval_id="a-1",
                run_id="r-1",
                tool_name="bash",
                status="approved",  # type: ignore[arg-type]
            )
