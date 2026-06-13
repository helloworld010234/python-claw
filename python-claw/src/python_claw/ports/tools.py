"""Ports for tool execution and tool registries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from python_claw.domain.message import ToolCall, ToolDefinition, ToolResult


class AgentTool(Protocol):
    """A single tool executable by the agent."""

    @property
    def definition(self) -> ToolDefinition:
        """Return the tool's metadata and input schema."""
        ...

    async def execute(self, call: ToolCall) -> ToolResult:
        """Execute the tool call and return a domain ToolResult."""
        ...


class ToolRegistry(Protocol):
    """Catalog of tools available during an agent run."""

    def get(self, name: str) -> AgentTool | None:
        """Return the tool registered under ``name``, or ``None``."""
        ...

    def list_definitions(self) -> list[ToolDefinition]:
        """Return metadata for all registered tools."""
        ...
