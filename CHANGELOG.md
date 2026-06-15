# Changelog

All notable changes to this project will be documented in this file.

## [0.5.7] — 2026-06-15

**Summary**: `mpg check` now uses a hybrid regex+AST detection engine — string-literal and comment false positives are eliminated via tokenize-based masking, and qualified/aliased forms (`typing.List`, `import typing as t; t.List`) are detected via AST import-alias resolution.

### Fixed

- `mpg check` no longer reports matches inside string literals or inline comments. A new tokenize-based `_mask_strings()` blanks the column ranges of STRING, FSTRING_MIDDLE, and COMMENT tokens before regex matching, replacing the previous `_string_lines()` which only skipped entire multi-line-string lines. Single-line strings like `x = "from typing import List"` previously triggered false positives; they are now correctly ignored while real code on the same or adjacent lines is still detected. (closes #121)

### Added

- AST-based qualified/aliased name detection: guides can now declare a `detect-names` frontmatter field listing fully qualified Python names (e.g. `typing.List`, `asyncio.gather`). `mpg check` builds an import-alias map from `ast.Import`/`ast.ImportFrom` nodes and resolves `ast.Name`/`ast.Attribute` references through it, matching qualified (`typing.List`), aliased (`import typing as t; t.List`), and direct (`from typing import List`) forms. Results are merged with regex matches (one per line, AST preferred). Six guides updated with detect-names: use-builtin-generics (11 names), pydantic-v2-validators, datetime-utc, taskgroup-over-gather, async-timeout-context, safe-subprocess. (closes #122)
- `_MAX_FILE_SIZE` (2 MB) guard: files exceeding 2 MB raise `CheckError` before reading, preventing memory issues on large generated files.
- `detect_names` field on `GuideMeta` with FQN validation (no bare names, wildcards, consecutive dots, or trailing parentheses).

## [0.5.6] — 2026-06-12

**Summary**: design.md output-schema examples now match the real CLI/MCP output, and CI builds the wheel and verifies the bundled assets so a packaging regression can no longer ship silently. No runtime behavior changes.

### Docs

- `docs/design.md` output-format examples corrected to match the actual serializers: the search example now lists all 11 fields (previously `tags`, `python`, `frequency`, and `snippet` were missing), the retrieve example's `source` field is shown as the dynamic `modern-python-guidance v<version>` instead of a stale hardcoded `v0.1.0`, and the previously undocumented `not_found` envelope (returned when some requested IDs do not exist) is now documented along with the `list` output schema. Also states explicitly that CLI `--format json` and the MCP tools emit the same JSON shapes, differing only in exit semantics. (closes #119)

### CI

- New `build` job builds the wheel (`python -m build`, pinned `build==1.5.0`, matching publish.yml), installs it non-editable, and runs `scripts/verify_wheel_assets.py` from outside the checkout to verify the bundled assets: `SKILL.md` presence, exact relative-path-set match of all guides against the checkout, the bundled rule file, and a functional `mpg list` against the installed wheel. Previously CI only ran tests against an editable install, so a broken `[tool.hatch.build.targets.wheel.sources]` mapping would have shipped a wheel with zero guides — failing silently with empty results at runtime. This gate covers the wheel install path only; sdist contents are not verified. (closes #120)

## [0.5.5] — 2026-06-11

**Summary**: `mpg setup` now detects cross-scope MCP registration shadowing, and the benchmark scorer no longer penalizes legitimate char-set strips.

### Fixed

- `mpg setup` warns when a same-name MCP registration in a higher-precedence scope (Claude Code resolves local > project > user) shadows the one it just wrote, naming the winning scope and the exact `claude mcp remove` command to recover. Previously a stale entry in another scope (e.g. a pre-0.5.4 bare-`mpg` registration in local scope) kept launching while setup printed success. Detection is advisory and fail-safe: warn-only with no auto-repair, never changes setup's exit code, issues no mutating subcommands, never echoes the winning entry's command line, degrades to a one-line note when `claude mcp get` fails, and stays silent on unparseable or unknown-scope output. With `--project-dir`, the check runs in the target project (local/project scopes are project-bound); dry-run skips detection entirely. (closes #131)
- Benchmark scorer: `check_SL3` no longer flags legitimate char-set strips (`line.rstrip("\n")`, `url.rstrip("/")`, whitespace sets like `"\r\n"`) as OUTDATED. It now matches only the removeprefix/removesuffix misuse class — a call with a single multi-char, non-whitespace string-literal argument such as `lstrip("test_")` or `rstrip(".json")`. Scorer-only change; previously reported benchmark figures were computed with the pre-fix scorer and are annotated in docs/benchmark-v5.md. (closes #129)

## [0.5.4] — 2026-06-10

### Fixed

- PostToolUse hook now auto-detects the project's target Python version from the nearest `pyproject.toml` (`requires-python`, Poetry constraints) or `.python-version`, walking up from the edited file, and filters guides accordingly. Previously every guide's patterns applied regardless of the project's Python floor, producing false positives such as union-syntax (`>=3.10`) warnings in a 3.8 project. The resolved target is shown in the hook summary line (`[target: py3.X]`), and version-config parsing never emits stderr noise on clean files. (closes #117)
- `mpg setup` now registers the MCP server with the absolute interpreter path (`<python> -m modern_python_guidance mcp`) instead of a bare `mpg` command, which Claude Code could not resolve when mpg was installed in a virtualenv (the MCP server process does not inherit venv activation). Re-running `mpg setup` replaces a stale existing registration in place (add → remove → retry only on "already exists", so a failed add never deletes a working entry), and the exact registered launch command is echoed for inspection. (closes #118)

### Migration

- If you ran `mpg setup` before this version and the MCP server is not loading (check with `claude mcp list`; most likely with venv installs), re-run `mpg setup` once — it replaces the old bare-`mpg` registration with the absolute interpreter path.

### Added

- `detect_configured_version()` internal helper (config-derived version only, no default fallback) with a 1 MiB size cap on config reads, and an upward config search bounded at depth 40.

## [0.5.3] — 2026-06-09

### Fixed

- MCP server: all 4 tool functions (`search_guides`, `retrieve_guides`, `list_guides`, `detect_python_version`) now validate argument types and return specific error messages instead of opaque "Internal error during tool execution". Covers string/integer/array type confusion, bool-as-int rejection (JSON Schema `"type": "integer"` excludes boolean), float rejection, `guide_ids` element type check, and `limit: null` crash path. (closes #115)
- CLI: `--limit` now rejects values outside 1-50 at parse time (`exit 2`) instead of silently accepting 0, negatives, or values above 50. Non-integer input (`--limit abc`, `--limit 1.5`) also rejected with clear error message. (closes #116)
- `search()`: negative `limit` no longer causes silent result truncation via Python slice semantics (`results[:-N]`). Defense-in-depth guard `limit = max(1, limit)` added.

### Added

- `_validate_type()` helper in MCP server with JSON Schema error terminology and `_JSON_TYPE_LABELS` for grammatically correct messages ("a string", "an integer", "an array").
- 30 new tests across 4 test files (1028 → 1058 total).

## [0.5.2] — 2026-06-08

### Changed

- SKILL.md trigger keywords narrowed to reduce false activations: standalone generic terms ("Python", "typing", "upgrade", "deprecated", "modernize") replaced with compound triggers ("modernize Python", "Python upgrade", etc.) and Python-specific additions ("pyproject.toml", "setup.py", "ruff"). Trigger count 13 → 15. Run `mpg setup` to update. (closes #32)

### Added

- Structural test V-011 guarding trigger keyword set against accidental drift (1034 total tests).

## [0.5.1] — 2026-06-07

### Fixed

- `mpg setup --project-dir /nonexistent` now emits a stderr warning ("directory does not exist and will be created") before proceeding. No warning when `--mcp-only` is used or when the directory exists. `--dry-run` also warns (typo detection). (closes #96)
- `check-python-release.yml`: curl now uses `-f` (fail on HTTP errors), `--retry 2`, `--connect-timeout 10`, `--max-time 30`. jq uses `capture()?` (try operator for non-matching release names) and `last // empty` (prevents `"null"` string on empty array). Pipeline errors are caught by `if !` wrapper instead of relying on `set -e` with bare assignment. (closes #97)

### Added

- 4 new tests (1032 total).

## [0.5.0] — 2026-06-06

### Changed

- Rules file (`rules/modern-python.md`) rewritten from full content (70 lines) to thin format (~30 lines): category index with all 41 guide IDs, top-5 high-frequency one-liner patterns, and MCP/CLI call-to-action. When the Rules file freezes as a static copy in git-tracked workspaces (symlink-to-file degradation), the thin format causes minimal stale-content damage — guide IDs rarely change. Run `mpg setup` to update the Rules file. (closes #109)

### Added

- `mpg hook claude-post-tool-use` subcommand: PostToolUse hook that reads stdin JSON from Claude Code, checks `.py` files for outdated patterns via `check_file()`, and surfaces findings as stderr feedback (exit 2). Non-Python files, missing files, and clean files produce no output (exit 0). No jq or shell wrapper required.
- `mpg check --quiet` flag: suppresses "No outdated patterns found." output on clean files in human format. JSON format is unaffected.
- `mpg setup` now prints a PostToolUse hook hint after successful setup.
- README: new "Recommended hooks" section with copy-pasteable `.claude/settings.json` example.
- 29 new tests (1028 total).

## [0.4.5] — 2026-06-06

### Fixed

- MCP `retrieve_guides` maxItems hardcoded to 41: replaced with `_guide_limit()` that derives the limit from actual guide count at runtime. `_get_tools()` dynamically injects `maxItems` and description into the `tools/list` schema. Adding new guides no longer requires updating `mcp_server.py`. (closes #98)
- `docs/design.md` out of sync with v0.4.4 implementation: consolidated overlapping non-goals, added `check`/`setup`/`uninstall` to CLI architecture diagram, added `check.py`, `setup_cmd.py`, `uninstall_cmd.py`, `mcp_server.py` to module responsibility table, fixed Layer 1 guide count from 16 to 18. (closes #99)

### Added

- 1 new test (1000 total).

## [0.4.4] — 2026-06-05

### Added

- Poetry constraint parsing: `detect_version()` now extracts the minimum Python version from `[tool.poetry.dependencies].python` instead of only logging a warning. Supported forms: caret (`^3.10`), tilde (`~3.11`), PEP 440 (`>=3.10,<3.14`), and dict-form (`{version = "^3.10"}`). Union operators (`||`) and unsupported formats warn and fall through to `.python-version` / default. (closes #95)
- Python 3.14 added to CI test matrix as a regular (non-allowed-failure) entry. Python 3.14 has been GA since 2025-10-07; pyproject.toml classifiers already declared support. (closes #94)
- 12 new tests (999 total).

## [0.4.3] — 2026-06-04

### Fixed

- MCP server crash on malformed `params` and `arguments`: non-dict values now return JSON-RPC -32602 instead of `TypeError`. `serve()` catch-all returns -32603 on unexpected errors. Notification messages (no `id`) are silently dropped per JSON-RPC 2.0 spec. (closes #91)
- `mpg check` false positives in multi-line docstrings: `check_file()` now uses `tokenize` to identify multi-line string token ranges and skips those lines. Single-line strings on code lines are still scanned. Tokenize failure (syntax errors, indentation errors) falls back to scanning all lines. (closes #92)
- Invalid PEP 440 specifiers in guide `python:` field silently treated as all-version compatible: `_build_meta()` now validates with `SpecifierSet` at parse time, raising `FrontmatterError`. Runtime `version_compatible()` narrows except from `(InvalidSpecifier, Exception)` to `(InvalidSpecifier, InvalidVersion)`. (closes #93)

### Added

- 53 new tests (987 total).

## [0.4.2] — 2026-06-04

### Fixed

- `_find_project_root()` escaping to `$HOME` when `~/.claude/` exists but the repo has no `.claude/` directory. Marker search is now per-level (nearest ancestor with any marker wins) instead of per-marker-type. If you previously ran `mpg setup` and have stale symlinks at `~/.claude/skills/modern-python-guidance` or `~/.claude/rules/modern-python.md`, remove them manually. (closes #90)

## [0.4.1] — 2026-06-03

### Added

- Body text search indexing: API names and identifiers appearing only in guide body text (e.g. `aiter_bytes`, `from_attributes`, `serialize_timestamp`) are now discoverable via `mpg search`. Body matches score at `WEIGHT_BODY=2`, below all frontmatter weights (TAG=10, ALIAS=8, TITLE=5, CATEGORY=3), preserving existing metadata-dominant ranking. Two-tier query tokenization handles code fragments like `aiter_bytes()` and `from_attributes=True`. (closes #22)
- 25 new tests (911 total).

## [0.4.0] — 2026-06-03

### Added

- `mpg check <file>` command: scan a Python file for outdated patterns using regex matching against guide definitions. Reports matches with line numbers, guide IDs, and inline snippets. Linter exit-code convention (0=clean, 1=findings, 2=error). Supports `--python-version` filtering, `--format json|human`, and `--exit-zero`. JSON envelope includes `file`, `mpg_version`, `matches`, and `summary` with `guide_ids` for batched `mpg retrieve`. (closes #21)
- `detect_patterns` field in guide frontmatter: 3-value semantics — curated regex list (26 guides), explicit opt-out `[]` (15 guides), or absent `None` (auto-extraction fallback for future guides). All patterns validated at parse time via `re.compile`.
- `CheckError` exception in check module for clean library-level error handling (file not found, binary file, read errors). CLI catches and converts to exit code 2.
- Structural tests: all 41 guides must have `detect_patterns` present, patterns must compile, must match at least one BAD line, and must NOT match any GOOD line.
- 205 new tests (886 total). Coverage: 92%+.

## [0.3.8] — 2026-06-02

### Added

- Fuzzy suggestions on retrieve miss: when a guide ID is not found, `difflib.get_close_matches` suggests up to 3 similar IDs (cutoff=0.5, case-insensitive). CLI shows "Did you mean:" in human format; JSON format and MCP tool return an envelope `{"results": [...], "not_found": [{"id": ..., "suggestions": [...]}]}`. Bare list preserved on all-found for backward compatibility. Exit code 1 when any ID is not found. (closes #14)

### Fixed

- `_handle_request` crash on non-dict JSON input (list, string, number, bool): now returns JSON-RPC -32600 "Invalid Request" error instead of `AttributeError`. Server continues processing subsequent requests. (closes #82)

## [0.3.7] — 2026-06-02

### Fixed

- `_read_message` CWE-674 recursion bug: ~1000 consecutive blank lines on MCP stdin would crash the server with `RecursionError`. Replaced recursive call with iterative `while` loop.

### Added

- 86 in-process unit tests for `cli.py` (33) and `mcp_server.py` (53), raising per-file coverage from 0% to 96%. Covers CLI dispatch, format auto-detection, search/retrieve/list subcommands, `_confine_path` security (8 patterns including symlink escape and CWD=/ guard), JSON-RPC framing, request handling, and serve loop recovery.

### Changed

- Coverage `fail_under` ratcheted from 59% to 92% (actual: 92.48%)
- CONTRIBUTING.md coverage gate updated to match

## [0.3.6] — 2026-05-31

### Added

- Rule-based delivery via symlink: `mpg setup` creates `.claude/rules/modern-python.md` that auto-injects modern Python guidance whenever Python-related files are touched, replacing reliance on probabilistic skill matching (closes #79)
- `setup_rules()` / `uninstall_rules()` mirroring skills symlink pattern
- `source.is_symlink()` security check to refuse symlink-to-symlink chains
- CI sync test enforcing SKILL.md body == rule body consistency
- 21 new tests (V-037 to V-060) for setup, uninstall, CI sync, and security

### Changed

- `--skills-only` now includes Rules (both are project-local artifacts)
- README updated to document 4 delivery methods (was 3)
- `--project-dir` help text updated to mention Skills/Rules symlinks

## [0.3.5] — 2026-05-30

### Added

- CI format gate: `ruff format --check src/ tests/` runs before linter, catching formatting regressions at PR time (closes #19)
- Coverage reporting: `pytest-cov` with branch coverage and `fail_under = 59%` ratchet threshold (closes #15)
- Guide structure validation: 248 parametrized tests validating all 41 guides — frontmatter fields, section order, code fences, H1 title, no duplicate IDs (closes #16)
- CONTRIBUTING.md: documented CI checks, format fix command, and guide count update step

### Changed

- Auto-formatted 12 existing source/test files with `ruff format` (whitespace only, no logic changes)
- CI step order: checkout → setup → install → **format check** → linter → tests (with `--cov`)

## [0.3.4] — 2026-05-30

### Fixed

- v0.3.3 shipped with `__version__ = "0.3.2"` in `__init__.py` (pyproject.toml was correct). This release fixes the version string

## [0.3.3] — 2026-05-30 (yanked — `__version__` mismatch)

### Added

- AST-based benchmark scorer (`bench/score_v5.py`): replaces grep-based V4 scorer with Python AST detection for structurally correct pattern matching — fixes 3 false-flag bugs on Opus 4.8 output (multiline code, docstring keywords, .venv contamination) (closes #59)
- VALID_ALT classification for SA2 (sync SQLAlchemy 2.0), TY6 (TypeGuard), AS3 (per-task except) — tracks valid alternatives separately from recommended patterns
- Benchmark prompt granularity testing (terse/normal/detailed) with V5 runner using isolated tmpdir for workspace safety
- V5 benchmark results on Opus 4.8: terse prompts +19pp, normal prompts +7pp strict modern rate ([details](docs/benchmark-v5.md))
- 83 new scorer tests (fixture parity, per-item golden tests, edge cases, import alias handling)
- Weekly GitHub Actions workflow to detect new Python stable releases and auto-create tracking issues (closes #70)

### Changed

- README benchmark highlight updated from V4 (+14.7pp) to V5 (79% → 98% on vague prompts, Opus 4.8)
- Ruff config: added per-file-ignores for `bench/*.py` (SIM102/SIM110)

## [0.3.2] — 2026-05-29

### Added

- `deferred-annotations` guide (PEP 649): drop unnecessary `from __future__ import annotations` on Python 3.14+ projects where annotations are lazily evaluated by default (closes #28)
- `template-strings` guide (PEP 750): use t-strings with processing functions for safe SQL/HTML parameterization instead of f-string interpolation (closes #28)
- Guide count: 39 → 41. Layer 1 coverage: 16 → 18

### Fixed

- `setup_mcp` now catches `OSError` from `subprocess.run`, matching `uninstall_mcp` behavior — an unexecutable `claude` binary produces a clean error message instead of a traceback (closes #65)
- MCP `retrieve_guides` schema `maxItems` and runtime guard updated from 39 to 41 to allow retrieval of all guides

## [0.3.1] — 2026-05-29

### Added

- `mpg uninstall` command: reverses `mpg setup` by deregistering the MCP server and removing the Agent Skills symlink in one command (closes #63)
- CLI flags: `--mcp-only`, `--skills-only`, `--project-dir`, `--dry-run` (no `--scope`; uninstall clears every scope `setup` can write to)
- Per-scope MCP deregistration (`claude mcp remove -s local` and `-s user`): a live probe showed `claude mcp remove` without a scope removes nothing when the server is registered in multiple scopes, so uninstall enumerates scopes explicitly to avoid leaving residue
- Symlink-only removal safety: only the symlink mpg created is removed (never its target), a non-symlink entity at the link path is refused, dangling symlinks are removed, and the parent `.claude/skills/` directory is preserved
- 26 new tests (V-015 through V-031)

### Changed

- Extracted shared `_skills_link_path` helper in `setup_cmd` so `setup` and `uninstall` resolve the Skills symlink location identically (no drift)

## [0.3.0] — 2026-05-28

### Added

- `mpg setup` command: one-command MCP server registration + Agent Skills symlink creation. Replaces 3-4 manual steps with `pip install modern-python-guidance && mpg setup` (closes #60)
- CLI flags: `--mcp-only`, `--skills-only`, `--scope {user,local}`, `--project-dir`, `--dry-run`
- Project root auto-detection (`.claude/` → `.git/` → `pyproject.toml` upward search) for correct Skills symlink placement from subdirectories
- Idempotent operation: re-running `mpg setup` skips already-correct state, replaces stale/broken symlinks, errors on non-symlink blockers
- Partial success handling: MCP and Skills run independently; one failure does not block the other
- 33 new tests for setup command (V-001 through V-014 verification points)

### Changed

- README Quick Start: reduced from 3 code blocks to 2 lines (`pip install` + `mpg setup`). Manual setup moved to collapsible `<details>` section

## [0.2.3] — 2026-05-28

### Fixed

- `fastapi-typed-state` guide: added missing Version Notes section (closes #13)
- `fastapi-typed-state` and `fastapi-lifespan` guides: corrected minimum version from FastAPI >= 0.93.0 to >= 0.94.0 (lifespan state dict requires Starlette >= 0.26.0, which FastAPI 0.93.0 excludes)

## [0.2.2] — 2026-05-28

### Changed

- Search response (MCP + CLI) now includes `tags`, `python`, `frequency`, and `snippet` fields for richer agent decision-making without requiring a follow-up retrieve call
- `dataclass-modern` guide rewritten: BAD/GOOD examples now center on immutable value objects (`frozen=True, slots=True, kw_only=True`), with decision criteria for when to use each flag; frequency upgraded to `high`
- README benchmark highlight now specifies "via Agent Skills" to accurately reflect the delivery method used in the A/B evaluation

### Added

- Snippet extraction: every guide produces a one-liner BAD → GOOD transformation preview (e.g. `@dataclass → @dataclass(frozen=True, slots=True, kw_only=True)`)
- 6 new tests: snippet non-empty invariant, exact fixture assertions, MCP/CLI enriched key validation

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

[0.3.2]: https://github.com/yottayoshida/modern-python-guidance/releases/tag/v0.3.2
[0.3.1]: https://github.com/yottayoshida/modern-python-guidance/releases/tag/v0.3.1
[0.3.0]: https://github.com/yottayoshida/modern-python-guidance/releases/tag/v0.3.0
[0.2.3]: https://github.com/yottayoshida/modern-python-guidance/releases/tag/v0.2.3
[0.2.2]: https://github.com/yottayoshida/modern-python-guidance/releases/tag/v0.2.2
[0.2.1]: https://github.com/yottayoshida/modern-python-guidance/releases/tag/v0.2.1
[0.2.0]: https://github.com/yottayoshida/modern-python-guidance/releases/tag/v0.2.0
[0.1.2]: https://github.com/yottayoshida/modern-python-guidance/releases/tag/v0.1.2
[0.1.1]: https://github.com/yottayoshida/modern-python-guidance/releases/tag/v0.1.1
[0.1.0]: https://github.com/yottayoshida/modern-python-guidance/releases/tag/v0.1.0
