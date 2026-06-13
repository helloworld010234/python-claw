"""Static tool registry for assembling the default tool set."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from python_claw.adapters.tools.file_tools import EditFileTool, ReadFileTool, WriteFileTool
from python_claw.adapters.tools.policy import DangerousCommandPolicy
from python_claw.adapters.tools.sandbox import WorkspaceSandbox
from python_claw.adapters.tools.shell import BashTool
from python_claw.domain.message import ToolDefinition
from python_claw.ports.tools import AgentTool


class StaticToolRegistry:
    """Immutable in-memory catalog of available tools."""

    def __init__(self, tools: Iterable[AgentTool]) -> None:
        seen: set[str] = set()
        self._tools: dict[str, AgentTool] = {}
        for tool in tools:
            name = tool.definition.name
            if name in seen:
                raise ValueError(f"duplicate tool name: {name}")
            seen.add(name)
            self._tools[name] = tool

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get(name)

    def list_definitions(self) -> list[ToolDefinition]:
        return [tool.definition for tool in self._tools.values()]


def create_default_tool_registry(
    workspace_root: str | Path,
    *,
    tool_timeout_seconds: int = 30,
    tool_max_output_chars: int = 8000,
) -> StaticToolRegistry:
    """Create the standard registry with read, write, edit and bash tools."""
    sandbox = WorkspaceSandbox(workspace_root)
    policy = DangerousCommandPolicy()
    tools: list[AgentTool] = [
        ReadFileTool(sandbox, max_output_chars=tool_max_output_chars),
        WriteFileTool(sandbox),
        EditFileTool(sandbox),
        BashTool(
            sandbox=sandbox,
            policy=policy,
            timeout_seconds=tool_timeout_seconds,
            max_output_chars=tool_max_output_chars,
        ),
    ]
    return StaticToolRegistry(tools)
