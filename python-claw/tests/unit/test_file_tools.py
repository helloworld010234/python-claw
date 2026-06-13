"""Tests for read_file and write_file tool adapters."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from python_claw.adapters.tools.file_tools import ReadFileTool, WriteFileTool
from python_claw.adapters.tools.sandbox import WorkspaceSandbox
from python_claw.domain.message import ToolCall


@pytest.fixture
def sandbox(tmp_path: Path) -> WorkspaceSandbox:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return WorkspaceSandbox(workspace)


@pytest.fixture
def read_tool(sandbox: WorkspaceSandbox) -> ReadFileTool:
    return ReadFileTool(sandbox, max_output_chars=10)


@pytest.fixture
def write_tool(sandbox: WorkspaceSandbox) -> WriteFileTool:
    return WriteFileTool(sandbox)


def test_read_file_success(read_tool: ReadFileTool, sandbox: WorkspaceSandbox) -> None:
    target = sandbox.root / "notes.txt"
    target.write_text("hello", encoding="utf-8")
    call = ToolCall(id="c1", name="read_file", arguments={"path": "notes.txt"})
    result = asyncio.run(read_tool.execute(call))
    assert result.is_error is False
    assert result.output == "hello"


def test_read_file_missing_argument(read_tool: ReadFileTool) -> None:
    call = ToolCall(id="c1", name="read_file", arguments={})
    result = asyncio.run(read_tool.execute(call))
    assert result.is_error is True
    assert "path" in result.output


def test_read_file_path_escape(read_tool: ReadFileTool) -> None:
    call = ToolCall(id="c1", name="read_file", arguments={"path": "../outside.txt"})
    result = asyncio.run(read_tool.execute(call))
    assert result.is_error is True
    assert "escapes workspace" in result.output


def test_read_file_truncates_long_output(sandbox: WorkspaceSandbox) -> None:
    tool = ReadFileTool(sandbox, max_output_chars=80)
    target = sandbox.root / "long.txt"
    target.write_text("x" * 200, encoding="utf-8")
    call = ToolCall(id="c1", name="read_file", arguments={"path": "long.txt"})
    result = asyncio.run(tool.execute(call))
    assert result.is_error is False
    assert result.output.endswith("...[truncated]")
    assert len(result.output) == 80


def test_write_file_success(write_tool: WriteFileTool, sandbox: WorkspaceSandbox) -> None:
    call = ToolCall(
        id="c1",
        name="write_file",
        arguments={"path": "notes.txt", "content": "hello world"},
    )
    result = asyncio.run(write_tool.execute(call))
    assert result.is_error is False
    assert "notes.txt" in result.output
    assert "11 chars" in result.output
    assert (sandbox.root / "notes.txt").read_text(encoding="utf-8") == "hello world"


def test_write_file_creates_parent_directories(
    write_tool: WriteFileTool, sandbox: WorkspaceSandbox
) -> None:
    call = ToolCall(
        id="c1",
        name="write_file",
        arguments={"path": "sub/dir/file.txt", "content": "nested"},
    )
    result = asyncio.run(write_tool.execute(call))
    assert result.is_error is False
    assert (sandbox.root / "sub" / "dir" / "file.txt").read_text(encoding="utf-8") == "nested"


def test_write_file_overwrites_existing_file(
    write_tool: WriteFileTool, sandbox: WorkspaceSandbox
) -> None:
    target = sandbox.root / "notes.txt"
    target.write_text("old", encoding="utf-8")
    call = ToolCall(
        id="c1",
        name="write_file",
        arguments={"path": "notes.txt", "content": "new"},
    )
    result = asyncio.run(write_tool.execute(call))
    assert result.is_error is False
    assert target.read_text(encoding="utf-8") == "new"


def test_write_file_missing_argument(write_tool: WriteFileTool) -> None:
    call = ToolCall(id="c1", name="write_file", arguments={"path": "x.txt"})
    result = asyncio.run(write_tool.execute(call))
    assert result.is_error is True
    assert "content" in result.output


def test_write_file_path_escape(write_tool: WriteFileTool) -> None:
    call = ToolCall(
        id="c1",
        name="write_file",
        arguments={"path": "../outside.txt", "content": "x"},
    )
    result = asyncio.run(write_tool.execute(call))
    assert result.is_error is True
    assert "escapes workspace" in result.output
