"""Tests for the workspace sandbox path validation."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from python_claw.adapters.tools.sandbox import SandboxViolation, WorkspaceSandbox


@pytest.fixture
def sandbox(tmp_path: Path) -> WorkspaceSandbox:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return WorkspaceSandbox(workspace)


def test_allows_path_inside_workspace(sandbox: WorkspaceSandbox) -> None:
    resolved = sandbox.resolve_read_path("notes.txt")
    assert resolved == sandbox.root / "notes.txt"


def test_allows_nested_path_inside_workspace(sandbox: WorkspaceSandbox) -> None:
    resolved = sandbox.resolve_write_path("sub/dir/file.txt")
    assert resolved == sandbox.root / "sub" / "dir" / "file.txt"


def test_rejects_empty_path(sandbox: WorkspaceSandbox) -> None:
    with pytest.raises(SandboxViolation, match="non-empty string"):
        sandbox.resolve_read_path("")


def test_rejects_non_string_path(sandbox: WorkspaceSandbox) -> None:
    with pytest.raises(SandboxViolation, match="non-empty string"):
        sandbox.resolve_read_path(None)  # type: ignore[arg-type]


def test_rejects_absolute_path(sandbox: WorkspaceSandbox) -> None:
    with pytest.raises(SandboxViolation, match="absolute paths"):
        sandbox.resolve_read_path("/etc/passwd")


def test_rejects_null_bytes(sandbox: WorkspaceSandbox) -> None:
    with pytest.raises(SandboxViolation, match="null bytes"):
        sandbox.resolve_read_path("file\x00.txt")


def test_rejects_dotdot_escape(sandbox: WorkspaceSandbox) -> None:
    with pytest.raises(SandboxViolation, match="escapes workspace"):
        sandbox.resolve_read_path("../outside.txt")


def test_rejects_deep_dotdot_escape(sandbox: WorkspaceSandbox) -> None:
    with pytest.raises(SandboxViolation, match="escapes workspace"):
        sandbox.resolve_read_path("a/b/../../../../outside.txt")


def test_rejects_parent_escape_for_write(sandbox: WorkspaceSandbox) -> None:
    with pytest.raises(SandboxViolation, match="escapes workspace"):
        sandbox.resolve_write_path("../outside.txt")


def test_rejects_symlink_escape(sandbox: WorkspaceSandbox) -> None:
    outside = sandbox.root.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = sandbox.root / "link.txt"
    try:
        os.symlink(outside, link)
    except OSError:
        pytest.skip("symbolic links not supported on this platform")

    with pytest.raises(SandboxViolation, match="escapes workspace"):
        sandbox.resolve_read_path("link.txt")


def test_rejects_symlink_directory_escape(sandbox: WorkspaceSandbox) -> None:
    outside_dir = sandbox.root.parent / "outside_dir"
    outside_dir.mkdir(exist_ok=True)
    link_dir = sandbox.root / "link_dir"
    try:
        os.symlink(outside_dir, link_dir, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links not supported on this platform")

    with pytest.raises(SandboxViolation, match="escapes workspace"):
        sandbox.resolve_write_path("link_dir/file.txt")


def test_write_parent_outside_workspace_is_rejected(sandbox: WorkspaceSandbox) -> None:
    with pytest.raises(SandboxViolation, match="escapes workspace"):
        sandbox.resolve_write_path("sub/../../outside.txt")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific junction escape test")
def test_rejects_windows_directory_junction_escape(sandbox: WorkspaceSandbox) -> None:
    """Directory junctions (and directory symlinks) on Windows must not escape."""
    outside_dir = sandbox.root.parent / "outside_dir_win"
    outside_dir.mkdir(exist_ok=True)
    link_dir = sandbox.root / "link_dir_win"

    symlink_error: OSError | None = None
    junction_error: OSError | None = None
    mklink_error: OSError | subprocess.CalledProcessError | None = None
    created = False

    try:
        os.symlink(outside_dir, link_dir, target_is_directory=True)
        created = True
    except OSError as exc:
        symlink_error = exc
        try:
            import _winapi

            _winapi.CreateJunction(str(link_dir), str(outside_dir))
            created = True
        except OSError as junction_exc:
            junction_error = junction_exc
            try:
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link_dir), str(outside_dir)],
                    check=True,
                    capture_output=True,
                )
                created = True
            except (OSError, subprocess.CalledProcessError) as mklink_exc:
                mklink_error = mklink_exc

    if not created:
        pytest.skip(
            "cannot create directory symlink or junction on this Windows environment: "
            f"symlink={symlink_error}; junction={junction_error}; mklink={mklink_error}"
        )

    with pytest.raises(SandboxViolation, match="escapes workspace"):
        sandbox.resolve_read_path("link_dir_win/file.txt")

    with pytest.raises(SandboxViolation, match="escapes workspace"):
        sandbox.resolve_write_path("link_dir_win/file.txt")
