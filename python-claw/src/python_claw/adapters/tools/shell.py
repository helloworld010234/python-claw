"""Shell tool adapter: bash."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from typing import Any

from python_claw.adapters.tools.policy import (
    CommandSafetyDecision,
    DangerousCommandPolicy,
    SafetyDecision,
)
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

            decision = self._policy.evaluate(command)
            if decision.decision is not CommandSafetyDecision.ALLOW:
                return self._make_policy_result(call.id, decision)

            output, is_error = await self._run(command)
            return ToolResult(tool_call_id=call.id, output=output, is_error=is_error)
        except SandboxViolation as exc:
            return ToolResult(tool_call_id=call.id, output=str(exc), is_error=True)

    def _require_str(self, arguments: Any, key: str) -> str:
        value = arguments.get(key)
        if not isinstance(value, str):
            raise SandboxViolation(f"{key} must be a string")
        return value

    def _make_policy_result(self, tool_call_id: str, decision: SafetyDecision) -> ToolResult:
        if decision.decision is CommandSafetyDecision.REQUIRE_APPROVAL:
            return ToolResult(
                tool_call_id=tool_call_id,
                output=f"command requires approval before execution: {decision.reason}",
                is_error=True,
            )
        return ToolResult(
            tool_call_id=tool_call_id,
            output=f"command denied by safety policy: {decision.reason}",
            is_error=True,
        )

    async def _run(self, command: str) -> tuple[str, bool]:
        spawn_kwargs: dict[str, Any] = {}
        if sys.platform == "win32":
            spawn_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            spawn_kwargs["start_new_session"] = True

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=self._sandbox.root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **spawn_kwargs,
            )
        except OSError as exc:
            return (
                f"failed to start command: {exc}",
                True,
            )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            await self._kill_process_tree(proc)
            return (
                f"command timed out after {self._timeout_seconds} seconds",
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

    async def _kill_process_tree(self, proc: asyncio.subprocess.Process) -> None:
        if sys.platform == "win32":
            await self._kill_windows_process_tree(proc)
        else:
            await self._kill_posix_process_tree(proc)

    async def _kill_windows_process_tree(self, proc: asyncio.subprocess.Process) -> None:
        try:
            taskkill = await asyncio.create_subprocess_exec(
                "taskkill",
                "/T",
                "/F",
                "/PID",
                str(proc.pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(taskkill.wait(), timeout=5)
            except TimeoutError:
                try:
                    taskkill.kill()
                except OSError:
                    pass
        except (OSError, FileNotFoundError):
            pass

        try:
            proc.kill()
        except OSError:
            pass

        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except TimeoutError:
            pass

    async def _kill_posix_process_tree(self, proc: asyncio.subprocess.Process) -> None:
        pgid: int | None = None
        try:
            pgid = os.getpgid(proc.pid)  # type: ignore[attr-defined]
        except ProcessLookupError:
            pass

        if pgid is not None:
            try:
                os.killpg(pgid, signal.SIGTERM)  # type: ignore[attr-defined]
            except (ProcessLookupError, PermissionError, OSError):
                pass

        try:
            proc.terminate()
        except (ProcessLookupError, OSError):
            pass

        try:
            await asyncio.wait_for(proc.wait(), timeout=1)
        except TimeoutError:
            if pgid is not None:
                try:
                    os.killpg(pgid, signal.SIGKILL)  # type: ignore[attr-defined]
                except (ProcessLookupError, PermissionError, OSError):
                    pass

            try:
                proc.kill()
            except (ProcessLookupError, OSError):
                pass

            try:
                await asyncio.wait_for(proc.wait(), timeout=2)
            except TimeoutError:
                pass
