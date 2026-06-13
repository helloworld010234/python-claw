"""Preflight guard for python-claw subtree commits and pushes."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_PREFIX = "python-claw/"
REQUIRED_SPLIT_ROOT_ENTRIES = {
    "PUSH-GUIDE.md",
    "pyproject.toml",
    "src",
    "tests",
    "uv.lock",
}
FORBIDDEN_UPSTREAM = "python-claw-origin/develop"


class GuardError(Exception):
    """Raised when a repository governance rule is violated."""


class RepoMode:
    """Resolved repository layout mode."""

    def __init__(self, *, root: Path, project_prefix: str, uses_subtree_split: bool) -> None:
        self.root = root
        self.project_prefix = project_prefix
        self.uses_subtree_split = uses_subtree_split

    @property
    def project_pathspec(self) -> str:
        if self.project_prefix:
            return self.project_prefix.rstrip("/")
        return "."

    @property
    def source_prefixes(self) -> tuple[str, str]:
        return (
            f"{self.project_prefix}src/",
            f"{self.project_prefix}tests/",
        )


def _run_git(
    repo_root: Path,
    args: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command from the monorepo root and return captured output."""
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _lines(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]


def find_untracked_source_paths(
    status_lines: list[str],
    source_prefixes: tuple[str, str] = ("python-claw/src/", "python-claw/tests/"),
) -> list[str]:
    """Return untracked source/test paths that must be staged before delivery."""
    untracked: list[str] = []
    for line in status_lines:
        if not line.startswith("?? "):
            continue
        path = line[3:].strip()
        if path.startswith(source_prefixes):
            untracked.append(path)
    return untracked


def find_out_of_scope_cached_paths(
    cached_lines: list[str],
    project_prefix: str = PROJECT_PREFIX,
) -> list[str]:
    """Return staged paths outside the python-claw subtree."""
    if not project_prefix:
        return []

    out_of_scope: list[str] = []
    for line in cached_lines:
        parts = line.split("\t")
        path = parts[-1].strip()
        if path and not path.startswith(PROJECT_PREFIX):
            out_of_scope.append(path)
    return out_of_scope


def validate_split_tree(entries: list[str]) -> None:
    """Validate that a subtree split looks like the remote repository root."""
    entry_set = set(entries)
    if "python-claw" in entry_set:
        raise GuardError("split root contains nested python-claw directory")

    missing_entries = sorted(REQUIRED_SPLIT_ROOT_ENTRIES - entry_set)
    if missing_entries:
        joined = ", ".join(missing_entries)
        raise GuardError(f"missing required split root entries: {joined}")


def validate_upstream(upstream: str | None, *, standalone: bool = False) -> None:
    """Prevent the monorepo branch from tracking the independent Python remote."""
    if standalone:
        return
    if upstream == FORBIDDEN_UPSTREAM:
        raise GuardError(
            "monorepo branch must not track python-claw-origin/develop; "
            "use subtree split for pushes"
        )


def _repo_root_from_project(project_root: Path) -> Path:
    """Return the Git root that owns the project directory."""
    result = _run_git(project_root, ["rev-parse", "--show-toplevel"])
    return Path(result.stdout.strip())


def _resolve_repo_mode(project_root: Path) -> RepoMode:
    """Detect whether the command runs in monorepo or standalone layout."""
    root = _repo_root_from_project(project_root)
    if (root / "python-claw" / "pyproject.toml").is_file():
        return RepoMode(root=root, project_prefix=PROJECT_PREFIX, uses_subtree_split=True)
    if (root / "pyproject.toml").is_file() and (root / "src").is_dir():
        return RepoMode(root=root, project_prefix="", uses_subtree_split=False)
    raise GuardError(
        "cannot detect python-claw repository layout; run from the monorepo root "
        "or from D:\\go-tiny-claw\\python-claw"
    )


def _current_upstream(repo_root: Path) -> str | None:
    result = _run_git(
        repo_root,
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _current_project_commit(mode: RepoMode) -> str:
    if not mode.uses_subtree_split:
        result = _run_git(mode.root, ["rev-parse", "HEAD"])
        return result.stdout.strip()

    result = _run_git(
        mode.root,
        ["subtree", "split", "--prefix=python-claw", "HEAD"],
    )
    split = result.stdout.splitlines()[-1].strip()
    if not split:
        raise GuardError("git subtree split did not return a commit")
    return split


def run_preflight(project_root: Path, *, remote_check: bool = False) -> None:
    """Run all repository governance checks."""
    mode = _resolve_repo_mode(project_root)

    status = _run_git(
        mode.root,
        [
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            mode.project_pathspec,
        ],
    )
    untracked_source_paths = find_untracked_source_paths(
        _lines(status.stdout),
        mode.source_prefixes,
    )
    if untracked_source_paths:
        joined = "\n  ".join(untracked_source_paths)
        raise GuardError(f"untracked source/test files must be staged:\n  {joined}")

    cached = _run_git(mode.root, ["diff", "--cached", "--name-status"])
    out_of_scope_paths = find_out_of_scope_cached_paths(
        _lines(cached.stdout),
        mode.project_prefix,
    )
    if out_of_scope_paths:
        joined = "\n  ".join(out_of_scope_paths)
        raise GuardError(f"cached paths outside python-claw are forbidden:\n  {joined}")

    validate_upstream(
        _current_upstream(mode.root),
        standalone=not mode.uses_subtree_split,
    )

    split = _current_project_commit(mode)
    split_tree = _run_git(mode.root, ["ls-tree", "--name-only", split])
    validate_split_tree(_lines(split_tree.stdout))

    if remote_check:
        remote_name = "python-claw-origin" if mode.uses_subtree_split else "origin"
        _run_git(mode.root, ["fetch", remote_name, "develop"])
        remote_ref = f"{remote_name}/develop"
        remote_tree = _run_git(
            mode.root,
            ["ls-tree", "--name-only", remote_ref],
        )
        validate_split_tree(_lines(remote_tree.stdout))

        diff = _run_git(
            mode.root,
            ["diff", "--exit-code", "--stat", remote_ref, split],
            check=False,
        )
        if diff.returncode not in (0, 1):
            raise GuardError(diff.stderr.strip() or "remote diff check failed")

    print(f"repo_guard=passed split={split}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate python-claw subtree commit/push governance.",
    )
    parser.add_argument(
        "--remote-check",
        action="store_true",
        help="also validate python-claw-origin/develop layout and compare split diff",
    )
    args = parser.parse_args(argv)

    try:
        run_preflight(Path.cwd(), remote_check=args.remote_check)
    except GuardError as exc:
        print(f"repo_guard=failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
