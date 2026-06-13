"""Unit tests for repository governance preflight checks."""

from __future__ import annotations

from scripts.repo_guard import (
    GuardError,
    find_out_of_scope_cached_paths,
    find_untracked_source_paths,
    validate_split_tree,
    validate_upstream,
)


def test_find_untracked_source_paths_reports_src_and_tests_only() -> None:
    status_lines = [
        "?? python-claw/src/python_claw/application/engine.py",
        "?? python-claw/tests/unit/test_agent_engine.py",
        "?? python-claw/.tmp/scratch.txt",
        " M python-claw/PUSH-GUIDE.md",
    ]

    assert find_untracked_source_paths(status_lines) == [
        "python-claw/src/python_claw/application/engine.py",
        "python-claw/tests/unit/test_agent_engine.py",
    ]


def test_find_out_of_scope_cached_paths_reports_non_python_claw_paths() -> None:
    cached_lines = [
        "M\tpython-claw/src/python_claw/application/engine.py",
        "A\tpython-claw/tests/unit/test_agent_engine.py",
        "M\tjava-claw/pom.xml",
        "A\tdocs/sdd/next.md",
    ]

    assert find_out_of_scope_cached_paths(cached_lines) == [
        "java-claw/pom.xml",
        "docs/sdd/next.md",
    ]


def test_validate_split_tree_rejects_nested_python_claw_directory() -> None:
    entries = ["python-claw", "pyproject.toml", "src", "tests", "uv.lock"]

    try:
        validate_split_tree(entries)
    except GuardError as exc:
        assert "nested python-claw" in str(exc)
    else:
        raise AssertionError("expected GuardError")


def test_validate_split_tree_requires_python_project_root_files() -> None:
    entries = ["pyproject.toml", "src", "uv.lock"]

    try:
        validate_split_tree(entries)
    except GuardError as exc:
        assert "missing required split root entries" in str(exc)
        assert "tests" in str(exc)
    else:
        raise AssertionError("expected GuardError")


def test_validate_upstream_rejects_python_claw_origin_tracking() -> None:
    try:
        validate_upstream("python-claw-origin/develop")
    except GuardError as exc:
        assert "must not track python-claw-origin/develop" in str(exc)
    else:
        raise AssertionError("expected GuardError")


def test_validate_upstream_allows_missing_or_other_upstream() -> None:
    validate_upstream(None)
    validate_upstream("origin/develop")
