# Contributing

## Project structure

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
└── guides/             # 41 guide files by category
```

See [docs/design.md](docs/design.md) for the full design document.

## Adding a new guide

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

## Running tests

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
ruff check src/ tests/
```
