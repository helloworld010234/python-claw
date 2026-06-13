"""Application-layer commands for agent execution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RunAgentCommand:
    """Command to start or continue an agent run.

    Attributes:
        run_id: Unique identifier for the run.
        session_id: Unique identifier for the session.
        prompt: User prompt that initiates the run.
        working_memory_limit: Optional override for the working memory window size.
    """

    run_id: str
    session_id: str
    prompt: str
    working_memory_limit: int | None = None

    def __post_init__(self) -> None:
        if not self.run_id or not self.run_id.strip():
            raise ValueError("RunAgentCommand.run_id must not be blank")
        if not self.session_id or not self.session_id.strip():
            raise ValueError("RunAgentCommand.session_id must not be blank")
        if self.prompt is None:
            raise ValueError("RunAgentCommand.prompt must not be None")
        if self.working_memory_limit is not None and self.working_memory_limit <= 0:
            raise ValueError(
                "RunAgentCommand.working_memory_limit must be positive, "
                f"got {self.working_memory_limit}"
            )
