"""Tests for the static tool registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from python_claw.adapters.tools.file_tools import WriteFileTool
from python_claw.adapters.tools.registry import StaticToolRegistry, create_default_tool_registry


def test_default_registry_has_four_tools(tmp_path: Path) -> None:
    registry = create_default_tool_registry(tmp_path)
    definitions = registry.list_definitions()
    names = {definition.name for definition in definitions}
    assert names == {"read_file", "write_file", "edit_file", "bash"}


def test_unknown_tool_returns_none(tmp_path: Path) -> None:
    registry = create_default_tool_registry(tmp_path)
    assert registry.get("missing") is None


def test_definitions_list_is_stable(tmp_path: Path) -> None:
    registry = create_default_tool_registry(tmp_path)
    first = registry.list_definitions()
    second = registry.list_definitions()
    assert [definition.name for definition in first] == [definition.name for definition in second]


def test_duplicate_tool_name_fails() -> None:
    from python_claw.adapters.tools.sandbox import WorkspaceSandbox

    workspace = WorkspaceSandbox(".")
    with pytest.raises(ValueError, match="duplicate tool name"):
        StaticToolRegistry([WriteFileTool(workspace), WriteFileTool(workspace)])


def test_get_returns_tool(tmp_path: Path) -> None:
    registry = create_default_tool_registry(tmp_path)
    tool = registry.get("read_file")
    assert tool is not None
    assert tool.definition.name == "read_file"
