---
name: modern-python-guidance
description: Version-aware BAD/GOOD pattern guides for modern Python. Use when writing, reviewing, or refactoring Python code to avoid outdated patterns (e.g. typing.List → list, @validator → @field_validator, setup.py → pyproject.toml). Triggers on "Python", "modernize", "upgrade", "deprecated", "pydantic", "fastapi", "httpx", "typing", "dataclass", "asyncio".
---

# Modern Python Guidance

Pre-generation design patterns that Ruff cannot auto-fix. Apply these transformations when writing or reviewing Python code.

## When to use

- Writing new Python code (use modern patterns from the start)
- Reviewing Python code (flag outdated patterns)
- Migrating from Pydantic V1 to V2
- Upgrading Python version (check which new features are available)
- Replacing legacy tooling (setup.py, flake8, pip)

## Embedded patterns (high-frequency, Ruff-uncovered)

### Pydantic V2 (>=3.9)

- `@validator("f")` → `@field_validator("f")`
- `@root_validator` → `@model_validator(mode="after")`
- `class Config:` → `model_config = ConfigDict(...)`
- `orm_mode` → `from_attributes`, `allow_population_by_field_name` → `populate_by_name`
- `.parse_obj(d)` → `.model_validate(d)`, `.parse_raw(j)` → `.model_validate_json(j)`
- `.dict()` → `.model_dump()`, `.json()` → `.model_dump_json()`
- `.schema()` → `.model_json_schema()`, `.copy()` → `.model_copy()`

### FastAPI (>=3.9)

- `@app.on_event("startup")`/`"shutdown"` → `@asynccontextmanager` lifespan + `FastAPI(lifespan=lifespan)`; yield dict becomes `request.state`
- `db: Session = Depends(get_db)` → `DbDep = Annotated[Session, Depends(get_db)]`; reusable type alias per PEP 593

### httpx

- Per-request `async with httpx.AsyncClient()` → shared `AsyncClient` with `base_url`
  - Caveat: shared client must be closed via `async with` or lifespan management

### asyncio (>=3.11)

- `await asyncio.gather(a(), b())` → `async with asyncio.TaskGroup() as tg:` + `tg.create_task()`; access results via `task.result()`
  - Caveat: 3.11+ only. `TaskGroup` cancels siblings on error and raises `ExceptionGroup`; `gather` preserves return order and supports `return_exceptions=True`

### Toolchain

- `setup.py` / `setup.cfg` → `pyproject.toml` with `[build-system]` + `[project]` (PEP 621)
- `subprocess.run(f"cmd {arg}", shell=True)` → `subprocess.run(["cmd", arg], check=True)`
  - Caveat: `shell=True` is valid when pipes/globs are needed; use `shlex.quote()` for user input

## All 30 guides by category

- **typing** (6): `use-builtin-generics`, `union-syntax`, `type-parameter-syntax`, `override-decorator`, `typeis-vs-typeguard`, `paramspec-decorators`
- **async** (3): `taskgroup-over-gather`, `exception-groups`, `async-timeout-context`
- **stdlib** (4): `datetime-utc`, `pathlib-over-os-path`, `tomllib-builtin`, `removeprefix-removesuffix`
- **data-structures** (3): `dict-merge-operator`, `match-case-patterns`, `dataclass-modern`
- **pydantic** (4): `pydantic-v2-validators`, `pydantic-v2-config`, `pydantic-v2-model-api`, `pydantic-v2-serialization`
- **fastapi** (3): `fastapi-lifespan`, `fastapi-annotated-depends`, `fastapi-typed-state`
- **httpx** (2): `httpx-async-client-reuse`, `httpx-streaming`
- **toolchain** (5): `pyproject-toml-over-setup`, `uv-over-pip`, `ruff-over-flake8`, `no-pickle`, `safe-subprocess`

For full code examples, use `mpg retrieve <guide-id>` or MCP tool `retrieve_guides`.
