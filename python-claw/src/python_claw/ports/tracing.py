"""Port for observability and tracing."""

from __future__ import annotations

from typing import Any, Protocol


class TraceRecorder(Protocol):
    """Recorder for structured trace events during an agent run."""

    def record(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Record a trace event for the given run."""
        ...
