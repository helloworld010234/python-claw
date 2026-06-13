"""Persistence adapter package.

Provides SQLAlchemy models, Alembic migrations, and repository adapters
for the core domain aggregates.
"""

from python_claw.adapters.persistence.database import Base, get_engine
from python_claw.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlMessageRepository,
    SqlRunRepository,
    SqlSessionRepository,
)

__all__ = [
    "Base",
    "SqlApprovalRepository",
    "SqlMessageRepository",
    "SqlRunRepository",
    "SqlSessionRepository",
    "get_engine",
]
