"""Port interfaces for external boundaries.

Future interfaces for LLM, tools, repositories, reporters, ChatOps, and tracing live here.
"""

from python_claw.ports.chatops import ChatOpsPort
from python_claw.ports.clock import Clock
from python_claw.ports.llm import LlmGateway
from python_claw.ports.reporters import Reporter
from python_claw.ports.repositories import (
    ApprovalRepository,
    MessageRepository,
    RunRepository,
    SessionRepository,
)
from python_claw.ports.tools import AgentTool, ToolRegistry
from python_claw.ports.tracing import TraceRecorder

__all__ = [
    "AgentTool",
    "ApprovalRepository",
    "ChatOpsPort",
    "Clock",
    "LlmGateway",
    "MessageRepository",
    "Reporter",
    "RunRepository",
    "SessionRepository",
    "ToolRegistry",
    "TraceRecorder",
]
