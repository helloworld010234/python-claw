"""SQLAlchemy declarative models for python-claw aggregates."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from python_claw.adapters.persistence.database import Base


class AgentSessionModel(Base):
    """Persisted session aggregate."""

    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    total_prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cost: Mapped[float] = mapped_column(default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    messages: Mapped[list[AgentMessageModel]] = relationship(
        back_populates="session",
        primaryjoin=(
            "and_(AgentMessageModel.session_id == AgentSessionModel.id,"
            " AgentMessageModel.run_id.is_(None))"
        ),
        foreign_keys="[AgentMessageModel.session_id]",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class AgentMessageModel(Base):
    """Persisted message entity belonging to a session or a run."""

    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("agent_sessions.id"), nullable=True
    )
    run_id: Mapped[str | None] = mapped_column(String, ForeignKey("agent_runs.id"), nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tool_calls_json: Mapped[str] = mapped_column(Text, default="null", nullable=False)
    tool_call_id: Mapped[str | None] = mapped_column(String, nullable=True)
    usage_json: Mapped[str] = mapped_column(Text, default="null", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    session: Mapped[AgentSessionModel | None] = relationship(back_populates="messages")
    run: Mapped[AgentRunModel | None] = relationship(back_populates="messages")

    __table_args__ = (
        Index(
            "ix_agent_messages_session_run_ordinal",
            "session_id",
            "run_id",
            "ordinal",
        ),
        Index(
            "ix_agent_messages_run_ordinal",
            "run_id",
            "ordinal",
        ),
    )


class AgentRunModel(Base):
    """Persisted agent run aggregate."""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("agent_sessions.id"), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    messages: Mapped[list[AgentMessageModel]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ApprovalRequestModel(Base):
    """Persisted human-in-the-loop approval request."""

    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("agent_runs.id"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    tool_arguments: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
