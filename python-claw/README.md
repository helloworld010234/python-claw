# python-claw

Python AgentOps Harness for `go-tiny-claw`.

This directory is the production-oriented Python rewrite workspace. It starts with an
architecture skeleton only: package layout, CLI/API shells, configuration, tests, and quality
gates. The Agent loop, tools, persistence repositories, real LLM adapters, and ChatOps adapters
are intentionally deferred to later milestones.

## Architecture

The package follows explicit clean architecture boundaries:

```text
domain <- application <- ports <- adapters <- config
```

- `domain`: pure domain model, no framework or SDK dependencies.
- `application`: use-case orchestration and future Harness services.
- `ports`: boundary interfaces for adapters.
- `adapters`: CLI, API, persistence, tool, LLM, reporter, ChatOps, and observability adapters.
- `config`: settings and object wiring.

## First Commands

Use a project-local virtual environment and cache. Do not write temporary artifacts to `C:`.

```powershell
$env:UV_CACHE_DIR="D:\go-tiny-claw\python-claw\.uv-cache"
$env:TEMP="D:\go-tiny-claw\python-claw\.tmp"
$env:TMP="D:\go-tiny-claw\python-claw\.tmp"
uv run --python 3.12 --extra dev pytest
uv run --python 3.12 --extra dev ruff check .
```

## Scope

Current scope is M1 skeleton only. Later milestones will add domain models, ports,
persistence, tools, Mock LLM engine flow, CLI/API run behavior, ChatOps, real LLM adapters,
observability, and benchmark support.
