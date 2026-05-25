# modern-python-guidance

[![CI](https://github.com/yottayoshida/modern-python-guidance/actions/workflows/ci.yml/badge.svg)](https://github.com/yottayoshida/modern-python-guidance/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/modern-python-guidance.svg)](https://pypi.org/project/modern-python-guidance/)
[![Python](https://img.shields.io/pypi/pyversions/modern-python-guidance.svg)](https://pypi.org/project/modern-python-guidance/)
[![License](https://img.shields.io/github/license/yottayoshida/modern-python-guidance.svg)](LICENSE)

LLMs often produce outdated Python — `typing.List` instead of `list`, `@validator` instead of `@field_validator`, `setup.py` instead of `pyproject.toml`. This tool provides 30 version-aware BAD/GOOD pattern guides that show the modern replacement, filtered by your project's Python version.

> **Note:** The tool itself requires Python 3.11+ to run. Guides cover patterns from Python 3.9 onward, and `--python-version` filters guides for your target environment.

## Quick start

```bash
# Install
pip install modern-python-guidance

# Search for a pattern
mpg search "typing list"
#   use-builtin-generics                     score=18.0  [typing]

# Get the full guide
mpg retrieve use-builtin-generics
# --- use-builtin-generics (version match: YES) ---
# ## BAD
# from typing import List, Dict, Optional
# ...
# ## GOOD
# names: list[str] = []
# ...
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

30 guides across 3 layers:

| Layer | Categories | Count | Examples |
|-------|-----------|-------|---------|
| **1 — stdlib** | typing, async, stdlib, data-structures | 16 | `list` over `List`, `match`/`case`, `TaskGroup` |
| **2 — frameworks** | pydantic, fastapi, httpx | 9 | Pydantic V2 migration, `Annotated[Depends]`, `AsyncClient` |
| **3 — toolchain** | toolchain | 5 | `uv` over `pip`, `ruff` over flake8, `pickle` avoidance |

Run `mpg list` to see all 30 guides, or [browse them on GitHub](skills/modern-python-guidance/guides/).

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

## MCP server

mpg includes a built-in [MCP](https://modelcontextprotocol.io) server that exposes all 4 commands as tools. AI agents (Claude Code, Cursor, Gemini CLI, etc.) can discover and call them directly.

### Setup with Claude Code

```bash
claude mcp add mpg -- mpg mcp
```

Or add to `.mcp.json` manually:

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

### Available tools

| Tool | Description |
|------|-------------|
| `search_guides` | Search guides by keyword with fuzzy matching |
| `retrieve_guides` | Get full BAD/GOOD content by guide ID |
| `list_guides` | Browse all guides, filter by category/version |
| `detect_python_version` | Auto-detect project Python version |

The MCP server uses stdio transport (JSON-RPC 2.0) and adds zero additional dependencies.

## Agent Skills integration

This project doubles as a [Claude Code Agent Skills](https://docs.anthropic.com/en/docs/claude-code) plugin. Install it into your project's `.claude/skills/` to give Claude automatic access to modern Python patterns when writing or reviewing code.

```bash
# Find where the package is installed
SKILL_DIR=$(python -c "from pathlib import Path; import modern_python_guidance; print(Path(modern_python_guidance.__file__).parent / 'skills' / 'modern-python-guidance')")

# Symlink into your project
ln -s "$SKILL_DIR" your-project/.claude/skills/modern-python-guidance
```

For other AI tools (Cursor, Copilot, etc.), use the CLI directly — pipe `mpg search` or `mpg retrieve` output into your workflow.

## Development

```bash
git clone https://github.com/yottayoshida/modern-python-guidance.git
cd modern-python-guidance
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
ruff check src/ tests/
```

### Project structure

```
src/modern_python_guidance/
├── cli.py              # Entry point (search, retrieve, list, detect-version, mcp)
├── mcp_server.py       # MCP server (JSON-RPC 2.0 over stdio)
├── frontmatter.py      # YAML-subset parser (no PyYAML dependency)
├── guide_index.py      # Guide discovery and indexing
├── search.py           # Weighted keyword search + fuzzy fallback
├── retrieve.py         # Guide retrieval and JSON rendering
├── version_detect.py   # Python version auto-detection
└── compat.py           # Shared helpers

skills/modern-python-guidance/
├── SKILL.md            # Agent Skills plugin entry point
└── guides/             # 30 guide files by category
```

See [docs/design.md](docs/design.md) for the full design document.

## Contributing

Contributions welcome! To add a new guide:

1. Create `skills/modern-python-guidance/guides/<category>/<id>.md`
2. Include YAML frontmatter with these fields:

| Field | Type | Values |
|-------|------|--------|
| `id` | string | Unique kebab-case identifier (must match filename) |
| `title` | string | Short descriptive title |
| `category` | string | Must match parent directory name |
| `layer` | int | 1 (stdlib), 2 (frameworks), 3 (toolchain) |
| `tags` | list | Search keywords |
| `aliases` | list | Alternate names (old API names, etc.) |
| `python` | string | Minimum version, e.g. `">=3.11"` |
| `frequency` | string | `high` (LLMs do this often), `medium`, `low` |

3. Write BAD/GOOD/Why/Version Notes sections
4. Run `pytest` to verify the guide parses correctly

## License

Apache-2.0 — see [LICENSE](LICENSE).
