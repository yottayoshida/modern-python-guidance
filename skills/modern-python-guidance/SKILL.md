---
name: modern-python-guidance
description: Version-aware BAD/GOOD pattern guides for modern Python. Use when writing, reviewing, or refactoring Python code to avoid outdated patterns (e.g. typing.List → list, @validator → @field_validator, setup.py → pyproject.toml). Triggers on "Python", "modernize", "upgrade", "deprecated", "pydantic", "fastapi", "httpx", "typing", "dataclass", "asyncio".
---

# Modern Python Guidance

Version-aware BAD → GOOD pattern guides for modern Python (3.9–3.13+).

When writing or reviewing Python code, consult these guides to ensure modern idioms are used instead of deprecated or outdated patterns. Each guide shows a concrete BAD example, the modern GOOD replacement, and explains why the change matters.

## When to use

- Writing new Python code (use modern patterns from the start)
- Reviewing Python code (flag outdated patterns)
- Migrating from Pydantic V1 to V2
- Upgrading Python version (check which new features are available)
- Replacing legacy tooling (setup.py, flake8, pip)

## Guide inventory (30 guides)

### Layer 1 — Standard Library & Language Features

| Category | Guide | Python | What it replaces |
|----------|-------|--------|-----------------|
| typing | `use-builtin-generics` | >=3.9 | `typing.List` → `list` |
| typing | `union-syntax` | >=3.10 | `Optional[X]` → `X \| None` |
| typing | `type-parameter-syntax` | >=3.12 | `TypeVar("T")` → `[T]` |
| typing | `override-decorator` | >=3.12 | manual override → `@override` |
| typing | `typeis-vs-typeguard` | >=3.13 | `TypeGuard` → `TypeIs` |
| typing | `paramspec-decorators` | >=3.10 | untyped decorators → `ParamSpec` |
| async | `taskgroup-over-gather` | >=3.11 | `gather()` → `TaskGroup` |
| async | `exception-groups` | >=3.11 | multi-error handling → `except*` |
| async | `async-timeout-context` | >=3.11 | `wait_for()` → `asyncio.timeout` |
| stdlib | `datetime-utc` | >=3.11 | `utcnow()` → `now(UTC)` |
| stdlib | `pathlib-over-os-path` | >=3.9 | `os.path` → `pathlib.Path` |
| stdlib | `tomllib-builtin` | >=3.11 | `toml` package → `tomllib` |
| stdlib | `removeprefix-removesuffix` | >=3.9 | `lstrip()`/slicing → `removeprefix()` |
| data-structures | `dict-merge-operator` | >=3.9 | `{**d1, **d2}` → `d1 \| d2` |
| data-structures | `match-case-patterns` | >=3.10 | nested if/isinstance → `match`/`case` |
| data-structures | `dataclass-modern` | >=3.10 | basic dataclass → `slots=True, kw_only=True` |

### Layer 2 — Popular Frameworks

| Category | Guide | What it replaces |
|----------|-------|-----------------|
| pydantic | `pydantic-v2-model-api` | `parse_obj()` → `model_validate()` |
| pydantic | `pydantic-v2-validators` | `@validator` → `@field_validator` |
| pydantic | `pydantic-v2-config` | `class Config` → `model_config = ConfigDict(...)` |
| pydantic | `pydantic-v2-serialization` | `json_encoders` → `@field_serializer` |
| fastapi | `fastapi-lifespan` | `@on_event` → lifespan context manager |
| fastapi | `fastapi-annotated-depends` | `Depends()` default → `Annotated[T, Depends()]` |
| fastapi | `fastapi-typed-state` | untyped `app.state` → typed state via lifespan |
| httpx | `httpx-async-client-reuse` | per-request client → shared `AsyncClient` |
| httpx | `httpx-streaming` | `response.content` → `client.stream()` |

### Layer 3 — Toolchain & Security

| Category | Guide | What it replaces |
|----------|-------|-----------------|
| toolchain | `pyproject-toml-over-setup` | `setup.py` → `pyproject.toml` |
| toolchain | `uv-over-pip` | `pip` → `uv` |
| toolchain | `ruff-over-flake8` | flake8+isort+black → `ruff` |
| toolchain | `no-pickle` | `pickle.load()` → safe alternatives |
| toolchain | `safe-subprocess` | `shell=True` → list arguments |

## How to look up a guide

Each guide is a markdown file in `guides/<category>/<id>.md` with YAML frontmatter containing:
- `id`: unique identifier
- `python`: minimum Python version (e.g. `">=3.11"`)
- `frequency`: how often LLMs generate the outdated pattern (`high`/`medium`/`low`)
- `layer`: 1 (stdlib), 2 (frameworks), 3 (toolchain)

### Reading a guide directly

Open `guides/<category>/<guide-id>.md` for the full BAD/GOOD comparison.

### Using the CLI

```bash
# Search by keyword
mpg search "typing list"

# Retrieve full guide content
mpg retrieve use-builtin-generics

# List all guides for a Python version
mpg list --python-version 3.11

# Detect project Python version
mpg detect-version
```

## Integration pattern for agents

When generating Python code:

1. Check if the target Python version is known (from `pyproject.toml`, `.python-version`, or context)
2. For each pattern you're about to write, check if a guide exists for a modern replacement
3. Use the GOOD pattern instead of the BAD pattern
4. If the target Python version is too old for the modern pattern, use the older pattern and note it

Example: if writing `from typing import List` for a Python 3.9+ project, use `list` instead (see `use-builtin-generics`).
