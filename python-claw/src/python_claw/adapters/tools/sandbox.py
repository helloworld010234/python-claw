"""Workspace sandbox for filesystem tool adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class SandboxViolation(Exception):  # noqa: N818
    """Raised when a tool request would escape the configured workspace."""


class WorkspaceSandbox:
    """Resolves tool-relative paths against a constrained workspace root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve(strict=False)

    def resolve_read_path(self, path: Any) -> Path:
        """Return a safe, absolute path for reading or editing.

        The target is not required to exist by this method; callers should verify
        existence and file type as needed.
        """
        return self._resolve(path, require_parent_only=False)

    def resolve_write_path(self, path: Any) -> Path:
        """Return a safe, absolute path for writing.

        The file itself may not exist yet, but its resolved parent directory must
        remain inside the workspace.
        """
        return self._resolve(path, require_parent_only=True)

    def _resolve(self, path: Any, *, require_parent_only: bool) -> Path:
        if not isinstance(path, str) or not path:
            raise SandboxViolation("path must be a non-empty string")

        if "\x00" in path:
            raise SandboxViolation("path contains null bytes")

        raw = Path(path)
        if raw.is_absolute() or path.startswith(("/", "\\")):
            raise SandboxViolation("absolute paths are not allowed")

        candidate = self.root / path
        resolved = candidate.resolve(strict=False)

        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise SandboxViolation(f"path escapes workspace: {path}") from exc

        if require_parent_only:
            parent = resolved.parent
            resolved_parent = parent.resolve(strict=False)
            try:
                resolved_parent.relative_to(self.root)
            except ValueError as exc:
                raise SandboxViolation(f"parent directory escapes workspace: {path}") from exc

        return resolved
