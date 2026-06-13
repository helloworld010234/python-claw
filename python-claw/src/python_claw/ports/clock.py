"""Port for time retrieval, kept domain-pure for testability."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Provider of the current time; adapters supply the real implementation."""

    def now(self) -> datetime:
        """Return the current datetime."""
        ...
