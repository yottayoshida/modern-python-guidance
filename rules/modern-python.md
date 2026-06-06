---
paths: ["**/*.py", "*.py", "**/pyproject.toml", "**/requirements*.txt", "**/setup.py", "**/setup.cfg", "**/.python-version", "**/Pipfile"]
---

# Modern Python Guidance

Pre-generation design patterns that Ruff cannot auto-fix. Apply these transformations when writing or reviewing Python code.

## Embedded patterns (high-frequency, Ruff-uncovered)

- `from typing import List, Dict` → `list[str]`, `dict[str, int]` (>=3.9)
- `@validator("f")` → `@field_validator("f")` (Pydantic V2)
- `datetime.utcnow()` → `datetime.now(UTC)` (>=3.11)
- `session.query(User).filter()` → `session.execute(select(User).where())` (SQLAlchemy 2.0)
- `subprocess.run(f"cmd {arg}", shell=True)` → `subprocess.run(["cmd", arg], check=True)`

## All 41 guides by category

- **async** (3): `async-timeout-context`, `exception-groups`, `taskgroup-over-gather`
- **data-structures** (3): `dataclass-modern`, `dict-merge-operator`, `match-case-patterns`
- **django** (3): `django-async-views`, `django-check-constraints`, `django-json-field`
- **fastapi** (3): `fastapi-annotated-depends`, `fastapi-lifespan`, `fastapi-typed-state`
- **httpx** (2): `httpx-async-client-reuse`, `httpx-streaming`
- **pydantic** (4): `pydantic-v2-config`, `pydantic-v2-model-api`, `pydantic-v2-serialization`, `pydantic-v2-validators`
- **pytest** (3): `pytest-parametrize`, `pytest-raises-match`, `pytest-tmp-path`
- **sqlalchemy** (3): `sqlalchemy-2-style`, `sqlalchemy-async-session`, `sqlalchemy-mapped-column`
- **stdlib** (5): `datetime-utc`, `pathlib-over-os-path`, `removeprefix-removesuffix`, `template-strings`, `tomllib-builtin`
- **toolchain** (5): `no-pickle`, `pyproject-toml-over-setup`, `ruff-over-flake8`, `safe-subprocess`, `uv-over-pip`
- **typing** (7): `deferred-annotations`, `override-decorator`, `paramspec-decorators`, `type-parameter-syntax`, `typeis-vs-typeguard`, `union-syntax`, `use-builtin-generics`

For full code examples, use `mpg retrieve <guide-id>` or MCP tool `retrieve_guides`.
