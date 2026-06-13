# Python Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Initialize the Python AgentOps Harness project skeleton without implementing the Agent loop, tools, persistence repositories, real LLM adapters, or ChatOps adapters.

**Architecture:** Establish a `src/python_claw` package with explicit clean architecture layers: `domain`, `application`, `ports`, `adapters`, and `config`. Add CLI/API shell entry points and architecture tests so later implementation work has enforceable boundaries.

**Tech Stack:** Python 3.12+, Typer, FastAPI, SQLAlchemy, Alembic, Pydantic Settings, pytest, ruff, mypy.

---

## File Structure

- Create `pyproject.toml` for package metadata, dependencies, entry points, pytest, ruff, and mypy configuration.
- Create `README.md` for the Python project scope and first commands.
- Create `.env.example` for non-secret configuration names.
- Create `.gitignore` inside `python-claw` for local Python artifacts.
- Create `alembic.ini` and `src/python_claw/adapters/persistence/migrations/README.md` as migration placeholders.
- Create `src/python_claw` package layers with `__init__.py` and package-local README files.
- Create `src/python_claw/adapters/api/app.py` with an app factory and health route only.
- Create `src/python_claw/adapters/cli/main.py` with a Typer app and help/version shell only.
- Create `src/python_claw/config/settings.py` with configuration loading only.
- Create tests under `tests/unit` and `tests/integration` to verify architecture boundaries and skeleton loading.

## Tasks

### Task 1: Add Skeleton Tests

- [x] Create tests that fail while the package skeleton does not exist.
- [x] Verify failure is caused by missing `python_claw` modules.

### Task 2: Add Packaging and Tooling

- [x] Create `pyproject.toml`.
- [x] Add Python-local `.gitignore`.
- [x] Add `.env.example`.
- [x] Add README.

### Task 3: Add Source Package Skeleton

- [x] Create layer packages.
- [x] Create API app factory shell.
- [x] Create CLI shell.
- [x] Create settings shell.

### Task 4: Verify Skeleton

- [x] Run pytest.
- [x] Run ruff.
- [x] Run compile check.
- [x] Inspect Git status for `python-claw`.
