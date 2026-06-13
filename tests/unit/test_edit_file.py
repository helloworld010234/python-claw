"""Tests for the edit_file tool adapter."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from python_claw.adapters.tools.file_tools import EditFileTool
from python_claw.adapters.tools.sandbox import WorkspaceSandbox
from python_claw.domain.message import ToolCall


@pytest.fixture
def sandbox(tmp_path: Path) -> WorkspaceSandbox:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return WorkspaceSandbox(workspace)


@pytest.fixture
def edit_tool(sandbox: WorkspaceSandbox) -> EditFileTool:
    return EditFileTool(sandbox)


def test_exact_replace(edit_tool: EditFileTool, sandbox: WorkspaceSandbox) -> None:
    target = sandbox.root / "file.txt"
    target.write_bytes(b"hello world")
    call = ToolCall(
        id="c1",
        name="edit_file",
        arguments={"path": "file.txt", "old_text": "world", "new_text": "universe"},
    )
    result = asyncio.run(edit_tool.execute(call))
    assert result.is_error is False
    assert "exact" in result.output
    assert target.read_text(encoding="utf-8") == "hello universe"


def test_normalized_replace(edit_tool: EditFileTool, sandbox: WorkspaceSandbox) -> None:
    target = sandbox.root / "file.txt"
    target.write_bytes(b"line1\r\nline2\r\nline3")
    call = ToolCall(
        id="c1",
        name="edit_file",
        arguments={
            "path": "file.txt",
            "old_text": "line2\nline3",
            "new_text": "LINE2\nLINE3",
        },
    )
    result = asyncio.run(edit_tool.execute(call))
    assert result.is_error is False
    assert "normalized" in result.output
    assert target.read_bytes() == b"line1\nLINE2\nLINE3"


def test_trim_replace(edit_tool: EditFileTool, sandbox: WorkspaceSandbox) -> None:
    target = sandbox.root / "file.txt"
    target.write_bytes(b"  hello  \n  world  ")
    call = ToolCall(
        id="c1",
        name="edit_file",
        arguments={
            "path": "file.txt",
            "old_text": "hello\nworld",
            "new_text": "hi\nthere",
        },
    )
    result = asyncio.run(edit_tool.execute(call))
    assert result.is_error is False
    assert "trim" in result.output
    assert target.read_bytes() == b"  hi\n  there"


def test_dedent_replace(edit_tool: EditFileTool, sandbox: WorkspaceSandbox) -> None:
    target = sandbox.root / "file.txt"
    target.write_bytes(b"  hello world\n  foo bar")
    call = ToolCall(
        id="c1",
        name="edit_file",
        arguments={
            "path": "file.txt",
            "old_text": "hello world\nfoo bar",
            "new_text": "goodbye world\nfarewell bar",
        },
    )
    result = asyncio.run(edit_tool.execute(call))
    assert result.is_error is False
    assert "dedent" in result.output
    assert target.read_bytes() == b"  goodbye world\n  farewell bar"


def test_zero_matches_fails(edit_tool: EditFileTool, sandbox: WorkspaceSandbox) -> None:
    target = sandbox.root / "file.txt"
    target.write_bytes(b"hello world")
    call = ToolCall(
        id="c1",
        name="edit_file",
        arguments={
            "path": "file.txt",
            "old_text": "missing",
            "new_text": "replacement",
        },
    )
    result = asyncio.run(edit_tool.execute(call))
    assert result.is_error is True


def test_multiple_matches_fails(edit_tool: EditFileTool, sandbox: WorkspaceSandbox) -> None:
    target = sandbox.root / "file.txt"
    target.write_bytes(b"foo foo foo")
    call = ToolCall(
        id="c1",
        name="edit_file",
        arguments={"path": "file.txt", "old_text": "foo", "new_text": "bar"},
    )
    result = asyncio.run(edit_tool.execute(call))
    assert result.is_error is True


def test_empty_old_text_fails(edit_tool: EditFileTool, sandbox: WorkspaceSandbox) -> None:
    target = sandbox.root / "file.txt"
    target.write_text("hello", encoding="utf-8")
    call = ToolCall(
        id="c1",
        name="edit_file",
        arguments={"path": "file.txt", "old_text": "", "new_text": "x"},
    )
    result = asyncio.run(edit_tool.execute(call))
    assert result.is_error is True
    assert "old_text" in result.output
