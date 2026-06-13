"""Shell tool adapter: bash."""

from __future__ import annotations

import asyncio
from typing import Any

from python_claw.adapters.tools.policy import DangerousCommandError, DangerousCommandPolicy
from python_claw.adapters.tools.sandbox import SandboxViolation, WorkspaceSandbox
from python_claw.domain.message import ToolCall, ToolDefinition, ToolResult


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    suffix = "...[truncated]"
    if limit <= len(suffix):
        return text[:limit]
    return text[: limit - len(suffix)] + suffix


def _json_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


class BashTool:
    """Run a non-interactive shell command inside the workspace."""

    NAME = "bash"

    def __init__(
        self,
        sandbox: WorkspaceSandbox,
        policy: DangerousCommandPolicy,
        timeout_seconds: int,
        max_output_chars: int,
    ) -> None:
        self._sandbox = sandbox
        self._policy = policy
        self._timeout_seconds = timeout_seconds
        self._max_output_chars = max_output_chars

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.NAME,
            description="Run a shell command in the workspace directory.",
            input_schema=_json_schema(
                {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    }
                },
                ["command"],
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            command = self._require_str(call.arguments, "command")
            if not command:
                return ToolResult(
                    tool_call_id=call.id,
                    output="command must not be empty",
                    is_error=True,
                )

            try:
                self._policy.check(command)
            except DangerousCommandError as exc:
                return ToolResult(tool_call_id=call.id, output=str(exc), is_error=True)

            output, is_error = await self._run(command)
            return ToolResult(tool_call_id=call.id, output=output, is_error=is_error)
        except SandboxViolation as exc:
            return ToolResult(tool_call_id=call.id, output=str(exc), is_error=True)

    def _require_str(self, arguments: Any, key: str) -> str:
        value = arguments.get(key)
        if not isinstance(value, str):
            raise SandboxViolation(f"{key} must be a string")
        return value

    async def _run(self, command: str) -> tuple[str, bool]:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=self._sandbox.root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self._timeout_seconds,
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return (
                    f"command timed out after {self._timeout_seconds} seconds",
                    True,
                )
        except OSError as exc:
            return (
                f"failed to start command: {exc}",
                True,
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        header = f"exit code: {proc.returncode}"
        body = f"stdout:\n{stdout}\nstderr:\n{stderr}"

        available = self._max_output_chars - len(header) - 1
        if available < 0:
            available = 0
        output = f"{header}\n{_truncate(body, available)}"

        return (
            output,
            proc.returncode != 0,
        )
