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

- Automated code transformation (this is a reference tool, not a codemod)
- Language Server Protocol integration
- Pattern detection in source code (no AST analysis)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ CLI (cli.py)                                            │
│  search │ retrieve │ list │ detect-version              │
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
3. `.python-version` file (pyenv/asdf convention)
4. Default: `3.11`

Poetry's caret syntax (`^3.11`) is detected but not parsed — the tool logs a warning and suggests using `--python-version` or adding `[project].requires-python`.

## Output format

The CLI defaults to JSON when piped and human-readable when attached to a TTY. The `--format` flag overrides this.

### JSON schema (search)

```json
[
  {
    "id": "use-builtin-generics",
    "title": "Use built-in generics instead of typing module",
    "category": "typing",
    "layer": 1,
    "score": 18.0,
    "token_estimate": 350,
    "fuzzy": false
  }
]
```

### JSON schema (retrieve)

```json
[
  {
    "id": "use-builtin-generics",
    "title": "Use built-in generics instead of typing module",
    "category": "typing",
    "layer": 1,
    "python": ">=3.9",
    "frequency": "high",
    "version_match": true,
    "content": "## BAD\n...\n## GOOD\n...",
    "token_estimate": 350,
    "source": "modern-python-guidance v0.1.0"
  }
]
```

## Guide layers

| Layer | Scope | Categories | Count |
|-------|-------|-----------|-------|
| 1 — stdlib | Python standard library | typing, async, stdlib, data-structures | 16 |
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
