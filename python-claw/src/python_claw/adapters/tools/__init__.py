"""Tool adapters package.

Provides filesystem and shell tools with workspace sandboxing and a static
registry for assembling the default tool set.
"""

from python_claw.adapters.tools.file_tools import EditFileTool, ReadFileTool, WriteFileTool
from python_claw.adapters.tools.policy import DangerousCommandError, DangerousCommandPolicy
from python_claw.adapters.tools.registry import StaticToolRegistry, create_default_tool_registry
from python_claw.adapters.tools.sandbox import SandboxViolation, WorkspaceSandbox
from python_claw.adapters.tools.shell import BashTool

__all__ = [
    "BashTool",
    "DangerousCommandError",
    "DangerousCommandPolicy",
    "EditFileTool",
    "ReadFileTool",
    "SandboxViolation",
    "StaticToolRegistry",
    "WorkspaceSandbox",
    "WriteFileTool",
    "create_default_tool_registry",
]
