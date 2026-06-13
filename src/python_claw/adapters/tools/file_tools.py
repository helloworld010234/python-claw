"""Filesystem tool adapters: read_file, write_file, edit_file."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

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


class ReadFileTool:
    """Read the contents of a workspace file as UTF-8 text."""

    NAME = "read_file"

    def __init__(self, sandbox: WorkspaceSandbox, max_output_chars: int) -> None:
        self._sandbox = sandbox
        self._max_output_chars = max_output_chars

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.NAME,
            description="Read a UTF-8 text file from the workspace.",
            input_schema=_json_schema(
                {"path": {"type": "string", "description": "Relative path to the file"}},
                ["path"],
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            path = self._require_str(call.arguments, "path")
            target = self._sandbox.resolve_read_path(path)
            if not target.exists():
                return ToolResult(
                    tool_call_id=call.id,
                    output=f"file does not exist: {path}",
                    is_error=True,
                )
            if not target.is_file():
                return ToolResult(
                    tool_call_id=call.id,
                    output=f"not a file: {path}",
                    is_error=True,
                )
            with target.open("r", encoding="utf-8", newline="") as handle:
                content = handle.read()
            return ToolResult(
                tool_call_id=call.id,
                output=_truncate(content, self._max_output_chars),
                is_error=False,
            )
        except SandboxViolation as exc:
            return ToolResult(tool_call_id=call.id, output=str(exc), is_error=True)
        except UnicodeDecodeError as exc:
            return ToolResult(tool_call_id=call.id, output=f"decode error: {exc}", is_error=True)
        except OSError as exc:
            return ToolResult(tool_call_id=call.id, output=f"read error: {exc}", is_error=True)

    def _require_str(self, arguments: Mapping[str, Any], key: str) -> str:
        value = arguments.get(key)
        if not isinstance(value, str):
            raise SandboxViolation(f"{key} must be a string")
        return value


class WriteFileTool:
    """Write UTF-8 text to a workspace file, creating parent directories if needed."""

    NAME = "write_file"

    def __init__(self, sandbox: WorkspaceSandbox) -> None:
        self._sandbox = sandbox

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.NAME,
            description="Write UTF-8 text to a file in the workspace.",
            input_schema=_json_schema(
                {
                    "path": {"type": "string", "description": "Relative path to the file"},
                    "content": {"type": "string", "description": "Text content to write"},
                },
                ["path", "content"],
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            path = self._require_str(call.arguments, "path")
            content = self._require_str(call.arguments, "content")
            target = self._sandbox.resolve_write_path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8", newline="") as handle:
                handle.write(content)
            rel_path = target.relative_to(self._sandbox.root)
            return ToolResult(
                tool_call_id=call.id,
                output=f"wrote {rel_path} ({len(content)} chars)",
                is_error=False,
            )
        except SandboxViolation as exc:
            return ToolResult(tool_call_id=call.id, output=str(exc), is_error=True)
        except OSError as exc:
            return ToolResult(tool_call_id=call.id, output=f"write error: {exc}", is_error=True)

    def _require_str(self, arguments: Mapping[str, Any], key: str) -> str:
        value = arguments.get(key)
        if not isinstance(value, str):
            raise SandboxViolation(f"{key} must be a string")
        return value


class EditFileTool:
    """Replace a unique occurrence of ``old_text`` with ``new_text`` in a workspace file.

    Matching strategies, in order:

    1. exact
    2. newline-normalized (``\\r\\n`` treated as ``\\n``)
    3. dedent (ignore leading whitespace per line)
    4. trim (ignore leading/trailing whitespace per line)
    """

    NAME = "edit_file"

    def __init__(self, sandbox: WorkspaceSandbox) -> None:
        self._sandbox = sandbox

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.NAME,
            description=(
                "Replace a unique occurrence of old_text with new_text in a workspace file."
            ),
            input_schema=_json_schema(
                {
                    "path": {"type": "string", "description": "Relative path to the file"},
                    "old_text": {
                        "type": "string",
                        "description": "Text to replace",
                    },
                    "new_text": {"type": "string", "description": "Replacement text"},
                },
                ["path", "old_text", "new_text"],
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        try:
            path = self._require_str(call.arguments, "path")
            old_text = self._require_str(call.arguments, "old_text")
            new_text = self._require_str(call.arguments, "new_text")

            if not old_text:
                return ToolResult(
                    tool_call_id=call.id,
                    output="old_text must not be empty",
                    is_error=True,
                )

            target = self._sandbox.resolve_read_path(path)
            if not target.exists():
                return ToolResult(
                    tool_call_id=call.id,
                    output=f"file does not exist: {path}",
                    is_error=True,
                )
            if not target.is_file():
                return ToolResult(
                    tool_call_id=call.id,
                    output=f"not a file: {path}",
                    is_error=True,
                )

            with target.open("r", encoding="utf-8", newline="") as handle:
                content = handle.read()
            try:
                result, strategy = _replace_unique(content, old_text, new_text)
            except _NoUniqueMatchError as exc:
                return ToolResult(
                    tool_call_id=call.id,
                    output=str(exc),
                    is_error=True,
                )
            with target.open("w", encoding="utf-8", newline="") as handle:
                handle.write(result)
            return ToolResult(
                tool_call_id=call.id,
                output=f"edited using {strategy} strategy",
                is_error=False,
            )
        except SandboxViolation as exc:
            return ToolResult(tool_call_id=call.id, output=str(exc), is_error=True)
        except OSError as exc:
            return ToolResult(tool_call_id=call.id, output=f"edit error: {exc}", is_error=True)

    def _require_str(self, arguments: Mapping[str, Any], key: str) -> str:
        value = arguments.get(key)
        if not isinstance(value, str):
            raise SandboxViolation(f"{key} must be a string")
        return value


def _replace_unique(content: str, old_text: str, new_text: str) -> tuple[str, str]:
    strategies = [
        ("exact", _exact_replace),
        ("normalized", _normalized_replace),
        ("dedent", _dedent_replace),
        ("trim", _trim_replace),
    ]
    for strategy_name, strategy_fn in strategies:
        try:
            return strategy_fn(content, old_text, new_text), strategy_name
        except _NoUniqueMatchError:
            continue
    raise _NoUniqueMatchError("old_text not found or appears multiple times")


class _NoUniqueMatchError(Exception):
    """Internal signal that a replacement strategy did not find a unique match."""


def _exact_replace(content: str, old_text: str, new_text: str) -> str:
    if content.count(old_text) == 1:
        return content.replace(old_text, new_text, 1)
    raise _NoUniqueMatchError()


def _normalized_replace(content: str, old_text: str, new_text: str) -> str:
    norm_content = content.replace("\r\n", "\n")
    norm_old = old_text.replace("\r\n", "\n")
    if norm_content.count(norm_old) == 1:
        return norm_content.replace(norm_old, new_text, 1)
    raise _NoUniqueMatchError()


def _dedent_replace(content: str, old_text: str, new_text: str) -> str:
    return _line_based_replace(
        content,
        old_text,
        new_text,
        transform=lambda line: line.lstrip(),
    )


def _trim_replace(content: str, old_text: str, new_text: str) -> str:
    return _line_based_replace(
        content,
        old_text,
        new_text,
        transform=lambda line: line.strip(),
    )


def _line_based_replace(
    content: str,
    old_text: str,
    new_text: str,
    transform: Callable[[str], str],
) -> str:
    content_lines = content.splitlines(keepends=True)
    old_lines = old_text.splitlines(keepends=True)

    def line_body(line: str) -> str:
        return transform(line.rstrip("\r\n"))

    transformed_content = [line_body(line) for line in content_lines]
    transformed_old = [line_body(line) for line in old_lines]

    matches = _find_subsequences(transformed_content, transformed_old)
    if len(matches) != 1:
        raise _NoUniqueMatchError()

    start = matches[0]
    end = start + len(old_lines)

    def leading_whitespace(line: str) -> str:
        stripped = line.rstrip("\r\n")
        trailing_start = len(stripped.lstrip())
        return stripped[: len(stripped) - trailing_start]

    indents = [leading_whitespace(content_lines[index]) for index in range(start, end)]
    new_lines = new_text.splitlines(keepends=True)

    for index, indent in enumerate(indents):
        if index >= len(new_lines):
            break
        new_line = new_lines[index]
        body = new_line.rstrip("\r\n")
        new_lines[index] = indent + body.lstrip() + new_line[len(body) :]

    transformed_new_text = "".join(new_lines)
    return "".join(content_lines[:start]) + transformed_new_text + "".join(content_lines[end:])


def _find_subsequences(haystack: list[str], needle: list[str]) -> list[int]:
    if not needle:
        return []
    matches: list[int] = []
    for index in range(len(haystack) - len(needle) + 1):
        if haystack[index : index + len(needle)] == needle:
            matches.append(index)
    return matches
