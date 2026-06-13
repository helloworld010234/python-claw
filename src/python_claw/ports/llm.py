"""Port for LLM interactions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from python_claw.domain.message import Message, ToolDefinition, Usage


class LlmGateway(Protocol):
    """Abstraction over an LLM provider.

    Implementations hide provider-specific APIs (OpenAI, Anthropic, etc.) and
    return domain Message objects.
    """

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
    ) -> tuple[Message, Usage]:
        """Send messages to the LLM and return the assistant response plus usage."""
        ...
