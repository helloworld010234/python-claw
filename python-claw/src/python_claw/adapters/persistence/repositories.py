"""SQLAlchemy implementations of repository ports."""

from __future__ import annotations

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session as DbSession

from python_claw.adapters.persistence import serialization as ser
from python_claw.adapters.persistence.models import (
    AgentMessageModel,
    AgentRunModel,
    AgentSessionModel,
    ApprovalRequestModel,
)
from python_claw.domain.approval import ApprovalRequest
from python_claw.domain.common import PythonClawDomainError
from python_claw.domain.message import Message
from python_claw.domain.run import AgentRun
from python_claw.domain.session import Session
from python_claw.ports.repositories import (
    ApprovalRepository,
    MessageRepository,
    RunRepository,
    SessionRepository,
)


class SqlSessionRepository(SessionRepository):
    """SQLAlchemy adapter for ``Session`` aggregate persistence."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save(self, session: Session) -> None:
        """Persist the session aggregate, upserting if it already exists."""
        with DbSession(self._engine, expire_on_commit=False) as db_session:
            existing = db_session.get(AgentSessionModel, session.id)
            if existing is None:
                model = ser.session_to_model(session)
                db_session.add(model)
            else:
                existing.status = session.status.value
                existing.total_prompt_tokens = session.total_usage.prompt_tokens
                existing.total_completion_tokens = session.total_usage.completion_tokens
                existing.total_cost = session.total_usage.cost
                existing.updated_at = ser.now_utc()
                db_session.execute(
                    delete(AgentMessageModel).where(
                        AgentMessageModel.session_id == session.id,
                        AgentMessageModel.run_id.is_(None),
                    )
                )
                for index, message in enumerate(session.messages):
                    db_session.add(
                        ser.message_to_model(
                            message,
                            ordinal=index,
                            session_id=session.id,
                        )
                    )
            db_session.commit()

    def get_by_id(self, session_id: str) -> Session | None:
        """Fetch a session by its identifier."""
        with DbSession(self._engine, expire_on_commit=False) as db_session:
            model = db_session.get(AgentSessionModel, session_id)
            if model is None:
                return None
            return ser.session_from_model(model)


class SqlMessageRepository(MessageRepository):
    """SQLAlchemy adapter for direct ``Message`` persistence within a session."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save(self, message: Message, session_id: str) -> None:
        """Persist a single session-level message, appending to the existing list."""
        with DbSession(self._engine, expire_on_commit=False) as db_session:
            session_model = db_session.get(AgentSessionModel, session_id)
            if session_model is None:
                raise PythonClawDomainError(
                    f"Cannot save message: session {session_id!r} not found"
                )
            max_ordinal = db_session.scalar(
                select(func.coalesce(func.max(AgentMessageModel.ordinal), -1)).where(
                    AgentMessageModel.session_id == session_id,
                    AgentMessageModel.run_id.is_(None),
                )
            )
            next_ordinal = 0 if max_ordinal is None else int(max_ordinal) + 1
            db_session.add(
                ser.message_to_model(
                    message,
                    ordinal=next_ordinal,
                    session_id=session_id,
                )
            )
            db_session.commit()

    def list_by_session(self, session_id: str) -> list[Message]:
        """Return all session-level messages in chronological order."""
        with DbSession(self._engine, expire_on_commit=False) as db_session:
            stmt = (
                select(AgentMessageModel)
                .where(
                    AgentMessageModel.session_id == session_id,
                    AgentMessageModel.run_id.is_(None),
                )
                .order_by(AgentMessageModel.ordinal.asc())
            )
            models = db_session.scalars(stmt).all()
            return [ser.message_from_model(model) for model in models]


class SqlRunRepository(RunRepository):
    """SQLAlchemy adapter for ``AgentRun`` aggregate persistence."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save(self, run: AgentRun) -> None:
        """Persist the run aggregate, upserting if it already exists."""
        with DbSession(self._engine, expire_on_commit=False) as db_session:
            existing = db_session.get(AgentRunModel, run.id)
            if existing is None:
                model = ser.run_to_model(run)
                db_session.add(model)
            else:
                existing.status = run.status.value
                existing.prompt = run.prompt
                existing.updated_at = ser.now_utc()
                db_session.execute(
                    delete(AgentMessageModel).where(
                        AgentMessageModel.run_id == run.id,
                    )
                )
                for index, message in enumerate(run.messages):
                    db_session.add(
                        ser.message_to_model(
                            message,
                            ordinal=index,
                            run_id=run.id,
                            session_id=run.session_id,
                        )
                    )
            db_session.commit()

    def get_by_id(self, run_id: str) -> AgentRun | None:
        """Fetch a run by its identifier."""
        with DbSession(self._engine, expire_on_commit=False) as db_session:
            model = db_session.get(AgentRunModel, run_id)
            if model is None:
                return None
            return ser.run_from_model(model)


class SqlApprovalRepository(ApprovalRepository):
    """SQLAlchemy adapter for ``ApprovalRequest`` aggregate persistence."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save(self, approval: ApprovalRequest) -> None:
        """Persist the approval request, upserting if it already exists."""
        with DbSession(self._engine, expire_on_commit=False) as db_session:
            existing = db_session.get(ApprovalRequestModel, approval.id)
            if existing is None:
                model = ser.approval_to_model(approval)
                db_session.add(model)
            else:
                existing.status = approval.status.value
                existing.tool_arguments = approval.tool_arguments
                existing.updated_at = ser.now_utc()
            db_session.commit()

    def get_by_id(self, approval_id: str) -> ApprovalRequest | None:
        """Fetch an approval request by its identifier."""
        with DbSession(self._engine, expire_on_commit=False) as db_session:
            model = db_session.get(ApprovalRequestModel, approval_id)
            if model is None:
                return None
            return ser.approval_from_model(model)
