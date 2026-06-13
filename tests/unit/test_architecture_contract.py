from __future__ import annotations

import ast
import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src" / "python_claw"
FORBIDDEN_CORE_IMPORTS = {
    "alembic",
    "anthropic",
    "fastapi",
    "openai",
    "sqlalchemy",
    "typer",
    "uvicorn",
}


def test_required_top_level_packages_are_importable() -> None:
    for module_name in [
        "python_claw",
        "python_claw.domain",
        "python_claw.application",
        "python_claw.ports",
        "python_claw.adapters",
        "python_claw.config",
    ]:
        importlib.import_module(module_name)


def test_domain_and_application_do_not_depend_on_adapter_libraries() -> None:
    checked_files = [
        *sorted((SOURCE_ROOT / "domain").rglob("*.py")),
        *sorted((SOURCE_ROOT / "application").rglob("*.py")),
    ]

    assert checked_files, "Expected domain and application skeleton packages to exist."

    violations: list[str] = []
    for source_file in checked_files:
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            imported_root = _imported_root(node)
            if imported_root in FORBIDDEN_CORE_IMPORTS:
                violations.append(
                    f"{source_file.relative_to(PROJECT_ROOT)} imports {imported_root}"
                )

    assert violations == []


def _imported_root(node: ast.AST) -> str | None:
    if isinstance(node, ast.Import):
        if not node.names:
            return None
        return node.names[0].name.split(".")[0]
    if isinstance(node, ast.ImportFrom) and node.module:
        return node.module.split(".")[0]
    return None
