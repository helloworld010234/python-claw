"""SQLAlchemy-backed implementations of the repository ports."""

from __future__ import annotations

from sqlalchemy import delete, func, select

from python_claw.domain.approval import ApprovalRequest, ApprovalStatus
from python_claw.domain.message import Message, Usage
from python_claw.domain.run import AgentRun, AgentRunStatus
from python_claw.domain.session import Session as DomainSession
from python_claw.domain.session import SessionStatus
from python_claw.ports.repositories import (
    ApprovalRepository,
    MessageRepository,
    RunRepository,
    SessionRepository,
)

from .models import (
    AgentRunRecord,
    ApprovalRequestRecord,
    RunMessageRecord,
    SessionMessageRecord,
    SessionRecord,
)
from .serialization import (
    message_from_dict,
    tool_calls_from_json,
    tool_calls_to_json,
)
from .session_factory import get_session_maker


class PersistenceError(Exception):
    """Raised when a persistence operation cannot be completed."""


def _message_kwargs(message: Message) -> dict[str, object]:
    """Return common column kwargs for a message row."""
    usage = message.usage
    return {
        "role": message.role.value,
        "content": message.content,
        "tool_call_id": message.tool_call_id,
        "tool_calls_json": tool_calls_to_json(message.tool_calls),
        "usage_prompt_tokens": usage.prompt_tokens if usage is not None else None,
        "usage_completion_tokens": usage.completion_tokens if usage is not None else None,
        "usage_cost": usage.cost if usage is not None else None,
    }


def _record_to_message_dict(record: SessionMessageRecord | RunMessageRecord) -> dict[str, object]:
    """Convert a message row back into the dictionary format expected by ``message_from_dict``."""
    usage: dict[str, object] | None = None
    if (
        record.usage_prompt_tokens is not None
        and record.usage_completion_tokens is not None
        and record.usage_cost is not None
    ):
        usage = {
            "prompt_tokens": record.usage_prompt_tokens,
            "completion_tokens": record.usage_completion_tokens,
            "cost": record.usage_cost,
        }
    return {
        "role": record.role,
        "content": record.content,
        "tool_calls": tool_calls_from_json(record.tool_calls_json),
        "tool_call_id": record.tool_call_id,
        "usage": usage,
    }


class SqlSessionRepository(SessionRepository):
    """SQLAlchemy implementation of ``SessionRepository``."""

    def __init__(self, engine_or_session_maker: object) -> None:
        """Create a repository bound to an engine or session factory."""
        from sqlalchemy.engine import Engine

        if isinstance(engine_or_session_maker, Engine):
            self._session_maker = get_session_maker(engine_or_session_maker)
        else:
            self._session_maker = engine_or_session_maker  # type: ignore[assignment]

    def save(self, session: DomainSession) -> None:
        """Persist or update a session and replace its messages atomically."""
        record = SessionRecord(
            id=session.id,
            status=session.status.value,
            prompt_tokens=session.total_usage.prompt_tokens,
            completion_tokens=session.total_usage.completion_tokens,
            cost=session.total_usage.cost,
        )

        with self._session_maker() as db_session:
            with db_session.begin():
                db_session.merge(record)
                db_session.execute(
                    delete(SessionMessageRecord).where(
                        SessionMessageRecord.session_id == session.id
                    )
                )
                for position, message in enumerate(session.messages):
                    db_session.add(
                        SessionMessageRecord(
                            session_id=session.id,
                            position=position,
                            **_message_kwargs(message),
                        )
                    )

    def get_by_id(self, session_id: str) -> DomainSession | None:
        """Fetch a session by id and reconstruct its aggregate."""
        with self._session_maker() as db_session:
            record = db_session.scalar(
                select(SessionRecord).where(SessionRecord.id == session_id)
            )
            if record is None:
                return None

            message_records = db_session.scalars(
                select(SessionMessageRecord)
                .where(SessionMessageRecord.session_id == session_id)
                .order_by(SessionMessageRecord.position)
            ).all()
            messages = [
                message_from_dict(_record_to_message_dict(msg_record))
                for msg_record in message_records
            ]

            return DomainSession.from_persistence(
                session_id=record.id,
                status=SessionStatus(record.status),
                messages=messages,
                total_usage=Usage(
                    prompt_tokens=record.prompt_tokens,
                    completion_tokens=record.completion_tokens,
                    cost=record.cost,
                ),
            )


class SqlMessageRepository(MessageRepository):
    """SQLAlchemy implementation of ``MessageRepository``."""

    def __init__(self, engine_or_session_maker: object) -> None:
        """Create a repository bound to an engine or session factory."""
        from sqlalchemy.engine import Engine

        if isinstance(engine_or_session_maker, Engine):
            self._session_maker = get_session_maker(engine_or_session_maker)
        else:
            self._session_maker = engine_or_session_maker  # type: ignore[assignment]

    def save(self, message: Message, session_id: str) -> None:
        """Append a message to the end of the given session."""
        with self._session_maker() as db_session:
            with db_session.begin():
                session_record = db_session.get(SessionRecord, session_id)
                if session_record is None:
                    raise PersistenceError(
                        f"Cannot save message: session {session_id!r} does not exist"
                    )
                if session_record.status == SessionStatus.ARCHIVED.value:
                    raise PersistenceError(
                        f"Cannot save message: session {session_id!r} is archived"
                    )

                max_position = db_session.scalar(
                    select(func.coalesce(func.max(SessionMessageRecord.position), -1)).where(
                        SessionMessageRecord.session_id == session_id
                    )
                )
                assert isinstance(max_position, int)
                db_session.add(
                    SessionMessageRecord(
                        session_id=session_id,
                        position=max_position + 1,
                        **_message_kwargs(message),
                    )
                )

                usage = message.usage
                if usage is not None:
                    session_record.prompt_tokens += usage.prompt_tokens
                    session_record.completion_tokens += usage.completion_tokens
                    session_record.cost += usage.cost

    def list_by_session(self, session_id: str) -> list[Message]:
        """Return all messages for a session in chronological order."""
        with self._session_maker() as db_session:
            records = db_session.scalars(
                select(SessionMessageRecord)
                .where(SessionMessageRecord.session_id == session_id)
                .order_by(SessionMessageRecord.position)
            ).all()
            return [
                message_from_dict(_record_to_message_dict(record)) for record in records
            ]


class SqlRunRepository(RunRepository):
    """SQLAlchemy implementation of ``RunRepository``."""

    def __init__(self, engine_or_session_maker: object) -> None:
        """Create a repository bound to an engine or session factory."""
        from sqlalchemy.engine import Engine

        if isinstance(engine_or_session_maker, Engine):
            self._session_maker = get_session_maker(engine_or_session_maker)
        else:
            self._session_maker = engine_or_session_maker  # type: ignore[assignment]

    def save(self, run: AgentRun) -> None:
        """Persist or update a run and replace its messages atomically."""
        record = AgentRunRecord(
            id=run.id,
            session_id=run.session_id,
            prompt=run.prompt,
            status=run.status.value,
        )

        with self._session_maker() as db_session:
            with db_session.begin():
                session_exists = db_session.scalar(
                    select(SessionRecord.id).where(SessionRecord.id == run.session_id)
                )
                if session_exists is None:
                    raise PersistenceError(
                        f"Cannot save run: session {run.session_id!r} does not exist"
                    )

                db_session.merge(record)
                db_session.execute(
                    delete(RunMessageRecord).where(RunMessageRecord.run_id == run.id)
                )
                for position, message in enumerate(run.messages):
                    db_session.add(
                        RunMessageRecord(
                            run_id=run.id,
                            position=position,
                            **_message_kwargs(message),
                        )
                    )

    def get_by_id(self, run_id: str) -> AgentRun | None:
        """Fetch a run by id and reconstruct its aggregate."""
        with self._session_maker() as db_session:
            record = db_session.scalar(
                select(AgentRunRecord).where(AgentRunRecord.id == run_id)
            )
            if record is None:
                return None

            message_records = db_session.scalars(
                select(RunMessageRecord)
                .where(RunMessageRecord.run_id == run_id)
                .order_by(RunMessageRecord.position)
            ).all()
            messages = [
                message_from_dict(_record_to_message_dict(msg_record))
                for msg_record in message_records
            ]

            return AgentRun.from_persistence(
                run_id=record.id,
                session_id=record.session_id,
                prompt=record.prompt,
                status=AgentRunStatus(record.status),
                messages=messages,
            )


class SqlApprovalRepository(ApprovalRepository):
    """SQLAlchemy implementation of ``ApprovalRepository``."""

    def __init__(self, engine_or_session_maker: object) -> None:
        """Create a repository bound to an engine or session factory."""
        from sqlalchemy.engine import Engine

        if isinstance(engine_or_session_maker, Engine):
            self._session_maker = get_session_maker(engine_or_session_maker)
        else:
            self._session_maker = engine_or_session_maker  # type: ignore[assignment]

    def save(self, approval: ApprovalRequest) -> None:
        """Persist or update an approval request."""
        record = ApprovalRequestRecord(
            id=approval.id,
            run_id=approval.run_id,
            tool_name=approval.tool_name,
            tool_arguments=approval.tool_arguments,
            status=approval.status.value,
        )

        with self._session_maker() as db_session:
            with db_session.begin():
                run_exists = db_session.scalar(
                    select(AgentRunRecord.id).where(AgentRunRecord.id == approval.run_id)
                )
                if run_exists is None:
                    raise PersistenceError(
                        f"Cannot save approval: run {approval.run_id!r} does not exist"
                    )

                db_session.merge(record)

    def get_by_id(self, approval_id: str) -> ApprovalRequest | None:
        """Fetch an approval request by id and reconstruct it."""
        with self._session_maker() as db_session:
            record = db_session.scalar(
                select(ApprovalRequestRecord).where(ApprovalRequestRecord.id == approval_id)
            )
            if record is None:
                return None

            return ApprovalRequest.from_persistence(
                approval_id=record.id,
                run_id=record.run_id,
                tool_name=record.tool_name,
                status=ApprovalStatus(record.status),
                tool_arguments=record.tool_arguments,
            )
