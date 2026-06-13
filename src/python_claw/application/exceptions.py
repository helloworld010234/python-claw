"""Application-layer exceptions."""

from __future__ import annotations


class AgentEngineError(Exception):
    """Raised when the agent engine fails to execute a run."""
