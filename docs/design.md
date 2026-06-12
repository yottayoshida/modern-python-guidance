# Design Document

## Problem

LLMs frequently generate outdated Python patterns: `typing.List` instead of `list`, `@validator` instead of `@field_validator`, `setup.py` instead of `pyproject.toml`. These patterns compile and run, so conventional linters don't flag them. Developers (and AI coding agents) need a reference that shows the modern replacement, filtered by the project's target Python version.

## Goals

1. Provide version-aware BAD/GOOD pattern guides as a CLI tool and Agent Skills plugin
2. Zero PyYAML dependency — parse guide frontmatter with a strict YAML subset
3. Single runtime dependency (`packaging`) for version specifier parsing
4. Deterministic, reproducible search results
5. JSON-first output for AI agent consumption, human-readable output for TTY

## Non-goals

- Automated code transformation / codemod (the `check` command scans for outdated patterns via regex + tokenize, but does not rewrite code)
- Language Server Protocol integration

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ CLI (cli.py)                                            │
│  search │ retrieve │ list │ detect-version │ check      │
│  setup │ uninstall                                      │
├─────────┴──────────┴──────┴─────────────────────────────┤
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ search.py    │  │ retrieve.py  │  │ version_      │  │
│  │ weighted     │  │ JSON render  │  │ detect.py     │  │
│  │ keyword +    │  │ + version    │  │ pyproject /   │  │
│  │ fuzzy        │  │ match flag   │  │ .python-ver   │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────────┘  │
│         │                 │                              │
│  ┌──────┴─────────────────┴──────────────────────────┐  │
│  │ guide_index.py — dynamic guide scanner            │  │
│  │ rglob("*.md") → parse → in-memory index           │  │
│  └──────────────────────┬────────────────────────────┘  │
│                         │                               │
│  ┌──────────────────────┴────────────────────────────┐  │
│  │ frontmatter.py — strict YAML-subset parser        │  │
│  │ key: value / key:\n  - item                       │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │ compat.py — version_compatible() + token_estimate │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ skills/modern-python-guidance/guides/                   │
│  typing/ async/ stdlib/ data-structures/                │
│  pydantic/ fastapi/ httpx/ toolchain/                   │
│  django/ sqlalchemy/ pytest/                            │
│  (41 guide files)                                       │
└─────────────────────────────────────────────────────────┘
```

## Module responsibilities

| Module | Responsibility |
|--------|---------------|
| `cli.py` | Argument parsing, output formatting (JSON/human), TTY detection, SIGPIPE handling |
| `frontmatter.py` | Strict YAML-subset parser. Only `key: value` and `  - item` constructs. Rejects everything else with line-numbered errors |
| `guide_index.py` | Discovers guide files via `rglob("*.md")`, parses each with `frontmatter.py`, builds an in-memory `GuideIndex`. Finds guides via `importlib.resources` (installed) or source tree fallback (development) |
| `search.py` | Weighted keyword search (tag=10, alias=8, title=5, category=3) with frequency boost. Falls back to fuzzy matching via `difflib.SequenceMatcher.ratio()` when no exact matches are found |
| `retrieve.py` | Renders guide content as JSON with version-match flag and token estimate |
| `version_detect.py` | Detects target Python version from `--python-version` flag, `pyproject.toml` (`requires-python`), `.python-version` file, or default (3.11) |
| `compat.py` | `version_compatible()` using `packaging.specifiers` and `token_estimate()` (chars / 4) |
| `check.py` | Scan a Python file for outdated patterns against guide definitions (regex + tokenize, not AST) |
| `setup_cmd.py` | Automate MCP server registration and Agent Skills symlink creation |
| `uninstall_cmd.py` | Reverse `mpg setup`: deregister the MCP server and remove the Skills symlink |
| `mcp_server.py` | MCP server — JSON-RPC 2.0 over stdio, zero external dependencies |

## Guide format

Each guide is a Markdown file with YAML-subset frontmatter:

```yaml
---
id: use-builtin-generics
title: Use built-in generics instead of typing module
category: typing
layer: 1
tags:
  - typing
  - generics
  - list
aliases:
  - typing.List
  - typing.Dict
python: ">=3.9"
frequency: high
pep: 585
---
```

### Required fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique kebab-case identifier, must match filename |
| `title` | string | Short descriptive title |
| `category` | string | Must match parent directory name |
| `layer` | int | 1 (stdlib), 2 (frameworks), 3 (toolchain) |
| `tags` | list | Search keywords |
| `python` | string | Minimum version specifier, e.g. `">=3.11"` |
| `frequency` | string | `high`, `medium`, or `low` |

### Optional fields

| Field | Type | Description |
|-------|------|-------------|
| `aliases` | list | Alternate names (old API names, etc.) |
| `pep` | int or list | Related PEP numbers |

### Body sections

Each guide body contains:

- `## BAD` — The outdated pattern with code example
- `## GOOD` — The modern replacement with code example
- `## Why` — Explanation of why the modern pattern is better
- `## Version Notes` — Python version requirements and migration path
- `## References` — Links to PEPs, documentation, etc.

## Search algorithm

### Primary search (weighted keyword)

For each query token, the search engine checks:

1. **Tags** (weight 10) — exact match against guide tags
2. **Aliases** (weight 8) — exact match or substring match (half weight)
3. **Title words** (weight 5) — exact match against title words
4. **Category** (weight 3) — exact match against category name

A frequency boost is added: high=+1.0, medium=+0.5, low=+0.0.

Results are sorted by `(-score, guide_id)` for deterministic ordering.

### Fuzzy fallback

When primary search returns no results, fuzzy fallback activates:

1. Build a pool of all guide IDs, titles, and tags
2. Use `difflib.get_close_matches()` with cutoff=0.4
3. Score each match using `SequenceMatcher.ratio()`
4. Sort by `(-score, guide_id)`, cap at 3 results

Fuzzy results are marked with `fuzzy: true` in the output.

## Version detection precedence

1. `--python-version` CLI flag (explicit override)
2. `pyproject.toml` `[project].requires-python` (PEP 621)
3. `pyproject.toml` `[tool.poetry.dependencies].python` — caret (`^3.10`), tilde (`~3.11`), and PEP 440 (`>=3.10,<3.14`) constraints are parsed to extract the minimum version. Dict-form (`{version = "^3.10"}`) is also supported. Union operators (`||`) are not supported and fall through with a warning.
4. `.python-version` file (pyenv/asdf convention)
5. Default: `3.11`

## Output format

The CLI defaults to JSON when piped and human-readable when attached to a TTY. The `--format` flag overrides this.

The MCP server tools (`search_guides`, `retrieve_guides`, `list_guides`) return the same JSON shapes as the CLI's `--format json` output. Only the exit semantics differ: the CLI exits 1 on empty results or missing IDs, while the MCP server returns the same payload as a non-error tool result.

These examples are real captured outputs: the field set is the contract (maintained against the serializers in `cli.py` and `mcp_server.py`), while values such as `score`, `token_estimate`, and `snippet` vary by query and guide revision.

### JSON schema (search)

First result of `mpg search "builtin generics" --format json` (the full output is an array of all matches):

```json
[
  {
    "id": "type-parameter-syntax",
    "title": "Use PEP 695 Type Parameter Syntax for Generics",
    "category": "typing",
    "layer": 1,
    "tags": ["type-hints", "generics", "typevar"],
    "python": ">=3.12",
    "frequency": "medium",
    "score": 15.5,
    "token_estimate": 273,
    "fuzzy": false,
    "snippet": "from typing import Generic, TypeVar → class Stack[T]:"
  }
]
```

### JSON schema (retrieve)

When all requested IDs are found, the output is a bare array (captured from `mpg retrieve use-builtin-generics --format json`, with `content` elided):

```json
[
  {
    "id": "use-builtin-generics",
    "title": "Use Built-in Generic Types Instead of typing Module",
    "category": "typing",
    "layer": 1,
    "python": ">=3.9",
    "frequency": "high",
    "version_match": true,
    "content": "## BAD\n...\n## GOOD\n...",
    "token_estimate": 261,
    "source": "modern-python-guidance v<version>"
  }
]
```

`source` reflects the installed package version at runtime (e.g. `modern-python-guidance v0.5.5`); do not pin fixtures or integrations to a literal version.

When one or more requested IDs are not found, the shape changes to an envelope (and the CLI exits 1):

```json
{
  "results": [{ "...": "found guides, same shape as above" }],
  "not_found": [
    { "id": "no-such-guide", "suggestions": ["django-async-views"] }
  ]
}
```

### JSON schema (list)

```json
[
  {
    "id": "use-builtin-generics",
    "title": "Use Built-in Generic Types Instead of typing Module",
    "category": "typing",
    "layer": 1,
    "python": ">=3.9",
    "frequency": "high"
  }
]
```

## Guide layers

| Layer | Scope | Categories | Count |
|-------|-------|-----------|-------|
| 1 — stdlib | Python standard library | typing, async, stdlib, data-structures | 18 |
| 2 — frameworks | Third-party frameworks | pydantic, fastapi, httpx, django, sqlalchemy, pytest | 18 |
| 3 — toolchain | Development tools | toolchain | 5 |

## Design decisions

### Why no PyYAML dependency?

Guide frontmatter uses a tiny subset of YAML (flat key-value pairs and simple lists). A strict regex-based parser is ~120 lines, has zero dependencies, and rejects anything outside the expected constructs with line-numbered errors. This keeps the install lightweight and avoids the `pyyaml` vs `ruamel.yaml` ecosystem split.

### Why `packaging` as the only dependency?

Version specifier comparison (`>=3.11`) is surprisingly complex. PEP 440 has pre-releases, post-releases, local versions, and wildcard exclusions. The `packaging` library is maintained by PyPA, already installed in most environments (it's a pip dependency), and handles all these edge cases correctly.

### Why char/4 for token estimates?

The `token_estimate` field helps AI agents decide whether to retrieve a guide based on context budget. The chars/4 heuristic is a rough but sufficient approximation for English-heavy technical text — accurate to within ±20% for the guide content, which is good enough for budget decisions.

### Why dynamic scanning instead of a static registry?

Guides are discovered at runtime via `rglob("*.md")` rather than maintained in a manifest file. This means adding a new guide is a single-file operation — no registry to update, no rebuild step. The index is built once per CLI invocation and cached in memory.

### Why `importlib.resources` for guide discovery?

When installed as a package, guides are bundled inside the wheel. `importlib.resources.files()` provides the standard way to locate package data files without relying on `__file__` paths (which break with zip imports). The `guide_index.py` module falls back to source tree paths for development.
