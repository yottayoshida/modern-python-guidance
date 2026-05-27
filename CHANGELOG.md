# Changelog

All notable changes to this project will be documented in this file.

## [0.2.1] — 2026-05-27

### Changed

- README rewrite: benefit-framed tagline, benchmark highlights, MCP-first quick start, persona-routed delivery methods
- Moved project structure and guide authoring spec from README to CONTRIBUTING.md
- Development section condensed to 5 lines + link

### Added

- CONTRIBUTING.md with project structure, guide authoring spec, and test instructions
- Benchmark results (+21.9pp) featured in README highlights

## [0.2.0] — 2026-05-27

### Added

- 9 new Layer 2 guides: Django (`django-json-field`, `django-async-views`, `django-check-constraints`), SQLAlchemy (`sqlalchemy-2-style`, `sqlalchemy-mapped-column`, `sqlalchemy-async-session`), pytest (`pytest-parametrize`, `pytest-tmp-path`, `pytest-raises-match`)
- SQLAlchemy 2.0 embedded patterns in SKILL.md (zero Ruff overlap)

### Changed

- Guide count: 30 → 39. Layer 2 coverage: 30% (9/30) → 46% (18/39)
- MCP server `retrieve_guides` max items: 30 → 39
- SKILL.md description trigger keywords: added "django", "sqlalchemy", "pytest"

## [0.1.2] — 2026-05-26

### Changed

- SKILL.md: replace inventory tables with 9 embedded BAD→GOOD arrow-list patterns (high-frequency × Ruff-uncovered) for pre-generation injection without MCP tool calls
- README: Quick start example changed from `use-builtin-generics` to `pydantic-v2-validators` (Layer 2 differentiation)

### Added

- MIT license (dual-licensed under Apache-2.0 OR MIT)
- `test_skill_sync.py`: 8 sync tests for SKILL.md ↔ guide file consistency (V-001/V-002/V-009/V-010)

## [0.1.1] — 2026-05-25

### Added

- Built-in MCP server (`mpg mcp`) exposing all 4 commands as tools over JSON-RPC 2.0 stdio transport — zero additional dependencies
- Setup: `claude mcp add mpg -- mpg mcp` for Claude Code, or add to `.mcp.json` manually
- 4 MCP tools: `search_guides`, `retrieve_guides`, `list_guides`, `detect_python_version`
- CWD confinement for `detect_python_version` (rejects absolute paths, traversal, symlink escape)
- Resilient message parsing: malformed messages are skipped instead of crashing the server
- JSON-RPC 2.0 notification compliance (no response for messages without `id`)
- 19 subprocess-based integration tests for MCP server

## [0.1.0] — 2026-05-24

Initial release.

### Added

- CLI tool with `search`, `retrieve`, `list`, and `detect-version` commands
- `mpg` short alias (both `mpg` and `modern-python-guidance` work)
- 30 version-aware BAD/GOOD pattern guides across 3 layers: stdlib (16), frameworks (9), toolchain (5)
- Weighted keyword search with fuzzy fallback via `difflib.SequenceMatcher`
- Python version auto-detection from `pyproject.toml`, `.python-version`, or `--python-version` flag
- JSON output (default when piped) and human-readable output (default for TTY)
- Agent Skills plugin (`SKILL.md`) for Claude Code integration
- Strict YAML-subset frontmatter parser (no PyYAML dependency)
- GitHub Actions CI (pytest + ruff on Python 3.11, 3.12, 3.13)

[0.2.0]: https://github.com/yottayoshida/modern-python-guidance/releases/tag/v0.2.0
[0.1.2]: https://github.com/yottayoshida/modern-python-guidance/releases/tag/v0.1.2
[0.1.1]: https://github.com/yottayoshida/modern-python-guidance/releases/tag/v0.1.1
[0.1.0]: https://github.com/yottayoshida/modern-python-guidance/releases/tag/v0.1.0
