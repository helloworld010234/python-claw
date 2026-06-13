"""Application-layer configuration for the agent engine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentEngineConfig:
    """Tunable parameters for the agent engine.

    Attributes:
        max_turns: Maximum number of agent turns before timing out.
        working_memory_limit: Default number of recent messages kept in the LLM context window.
    """

    max_turns: int = 20
    working_memory_limit: int = 20

    def __post_init__(self) -> None:
        if self.max_turns <= 0:
            raise ValueError(
                f"AgentEngineConfig.max_turns must be positive, got {self.max_turns}"
            )
        if self.working_memory_limit <= 0:
            raise ValueError(
                "AgentEngineConfig.working_memory_limit must be positive, "
                f"got {self.working_memory_limit}"
            )
