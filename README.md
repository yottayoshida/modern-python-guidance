# modern-python-guidance

[![CI](https://github.com/yottayoshida/modern-python-guidance/actions/workflows/ci.yml/badge.svg)](https://github.com/yottayoshida/modern-python-guidance/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/modern-python-guidance.svg)](https://pypi.org/project/modern-python-guidance/)
[![Python](https://img.shields.io/pypi/pyversions/modern-python-guidance.svg)](https://pypi.org/project/modern-python-guidance/)
[![License](https://img.shields.io/github/license/yottayoshida/modern-python-guidance.svg)](LICENSE)

Stop your AI from writing `typing.List`, `@validator`, and `setup.py`. 39 version-aware BAD/GOOD pattern guides that teach AI coding agents to write modern Python — delivered via MCP, CLI, or Agent Skills.

## Highlights

- **Measurable impact**: +14.7pp overall improvement in A/B benchmark with 38 scored items ([details](docs/benchmark-evaluation.md)). Largest variant (FastAPI, 32 items): Control 60.4% → Treatment 82.3%
- **39 guides** across stdlib, Pydantic, FastAPI, Django, SQLAlchemy, pytest, and toolchain
- **Version-aware**: auto-detects your project's Python version and filters guides accordingly
- **3 delivery methods**: MCP server, CLI, Agent Skills plugin
- **Not Ruff**: Ruff auto-fixes syntax (`List` → `list`). mpg guides design decisions that Ruff can't touch — `TaskGroup` over `gather`, Pydantic V2 migration, SQLAlchemy 2.0 style

> **Note:** The tool itself requires Python 3.11+ to run. Guides cover patterns from Python 3.9 onward, and `--python-version` filters guides for your target environment.

## Quick start

### MCP (for AI coding agents)

Install, then register the MCP server with your agent:

```bash
pip install modern-python-guidance
```

**Claude Code:**
```bash
claude mcp add mpg -- mpg mcp
```

**Other MCP-compatible agents** (Cursor, Windsurf, etc.) — add to your MCP config:
```json
{
  "mcpServers": {
    "mpg": {
      "command": "mpg",
      "args": ["mcp"]
    }
  }
}
```

Your agent gets access to `search_guides`, `retrieve_guides`, `list_guides`, and `detect_python_version`.

### CLI

```bash
pip install modern-python-guidance

# Search for a pattern
mpg search "pydantic validator"

# Get the full guide
mpg retrieve pydantic-v2-validators
```

### Agent Skills (Claude Code plugin)

```bash
# Symlink into your project
SKILL_DIR=$(python -c "from pathlib import Path; import modern_python_guidance; print(Path(modern_python_guidance.__file__).parent / 'skills' / 'modern-python-guidance')")
ln -s "$SKILL_DIR" your-project/.claude/skills/modern-python-guidance
```

`mpg` is the short alias for `modern-python-guidance`. Both work.

## CLI usage

```bash
# Search guides by keyword
mpg search "pydantic validator"

# Retrieve a specific guide (full BAD/GOOD content)
mpg retrieve use-builtin-generics

# List all guides compatible with your Python version
mpg list --python-version 3.11

# Auto-detect project Python version from pyproject.toml / .python-version
mpg detect-version

# Filter by category
mpg search "timeout" --category async

# JSON output (default when piped, explicit with --format)
mpg search "typing" --format json | jq '.[0].id'
```

## Guide coverage

39 guides across 3 layers:

| Layer | Categories | Count | Examples |
|-------|-----------|-------|---------|
| **1 — stdlib** | typing, async, stdlib, data-structures | 16 | `list` over `List`, `match`/`case`, `TaskGroup` |
| **2 — frameworks** | pydantic, fastapi, httpx, django, sqlalchemy, pytest | 18 | Pydantic V2 migration, SQLAlchemy 2.0 style, `Annotated[Depends]` |
| **3 — toolchain** | toolchain | 5 | `uv` over `pip`, `ruff` over flake8, `pickle` avoidance |

Run `mpg list` to see all 39 guides, or [browse them on GitHub](skills/modern-python-guidance/guides/).

## Version-aware filtering

Guides specify their minimum Python version. The CLI auto-detects your project's version from (in order):

1. `--python-version` flag
2. `pyproject.toml` `requires-python`
3. `.python-version` file
4. Default: 3.11

```bash
# Only shows guides compatible with Python 3.9
mpg list --python-version 3.9
# Excludes: TaskGroup (3.11+), match/case (3.10+), etc.
```

## Development

```bash
git clone https://github.com/yottayoshida/modern-python-guidance.git
cd modern-python-guidance
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for project structure and guide authoring details.

## License

Apache-2.0 OR MIT — see [LICENSE](LICENSE) and [LICENSE-MIT](LICENSE-MIT).
