"""core persistence

Revision ID: 0001
Revises:
Create Date: 2026-06-13 16:42:41.620909+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("total_prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("total_completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_cost", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls_json", sa.Text(), nullable=False),
        sa.Column("tool_call_id", sa.String(), nullable=True),
        sa.Column("usage_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_messages_session_run_ordinal",
        "agent_messages",
        ["session_id", "run_id", "ordinal"],
    )
    op.create_index(
        "ix_agent_messages_run_ordinal",
        "agent_messages",
        ["run_id", "ordinal"],
    )
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("tool_arguments", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("approval_requests")
    op.drop_index("ix_agent_messages_run_ordinal", table_name="agent_messages")
    op.drop_index("ix_agent_messages_session_run_ordinal", table_name="agent_messages")
    op.drop_table("agent_messages")
    op.drop_table("agent_runs")
    op.drop_table("agent_sessions")
