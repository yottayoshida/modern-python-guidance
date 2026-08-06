# modern-python-guidance

[![CI](https://github.com/yottayoshida/modern-python-guidance/actions/workflows/ci.yml/badge.svg)](https://github.com/yottayoshida/modern-python-guidance/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/modern-python-guidance.svg)](https://pypi.org/project/modern-python-guidance/)
[![Python](https://img.shields.io/pypi/pyversions/modern-python-guidance.svg)](https://pypi.org/project/modern-python-guidance/)
[![License](https://img.shields.io/github/license/yottayoshida/modern-python-guidance.svg)](LICENSE)

Stop your AI from writing `typing.List`, `@validator`, and `setup.py`. 41 version-aware BAD/GOOD pattern guides that teach AI coding agents to write modern Python — delivered via MCP, CLI, or Agent Skills.

## Highlights

- **Measurable impact**: AI writes modern Python 98% of the time with mpg, vs 79% without — even with vague prompts (Opus 4.8, [V5 benchmark details](docs/benchmark-v5.md))
- **41 guides** across stdlib, Pydantic, FastAPI, Django, SQLAlchemy, pytest, and toolchain
- **Version- and dependency-aware**: filters Python-version-incompatible guidance and qualifies framework/tool guidance from project evidence
- **4 delivery methods**: MCP server, CLI, Agent Skills, and Rules (auto-injects on `.py` file touch)
- **Not Ruff**: Ruff auto-fixes syntax (`List` → `list`). mpg guides design decisions that Ruff can't touch — `TaskGroup` over `gather`, Pydantic V2 migration, SQLAlchemy 2.0 style

> **Note:** The tool itself requires Python 3.11+ to run. Guides cover patterns from Python 3.9 onward, and `--python-version` filters guides for your target environment.

## Quick start

### Claude Code (recommended)

```bash
pip install modern-python-guidance
mpg setup
```

This registers the MCP server, links Agent Skills, creates a Rules file (`.claude/rules/modern-python.md`), and registers a PostToolUse hook in one command. The Rules file auto-injects modern Python guidance whenever you touch Python-related files, and the hook actively checks every edited `.py` file against the full 41-guide catalog (see [PostToolUse hook](#posttooluse-hook) below). Start a new Claude Code session afterwards — newly registered MCP servers, skills, rules, and hooks take effect on the next launch.

### CLI

```bash
pip install modern-python-guidance
mpg search "pydantic validator"
mpg retrieve pydantic-v2-validators
```

`mpg` is the short alias for `modern-python-guidance`. Both work.

<details>
<summary>Manual setup / other agents</summary>

**MCP registration (Claude Code):**
```bash
# uv tool / pipx installs (mpg is on PATH):
claude mcp add mpg -- mpg mcp

# venv installs — Claude Code spawns MCP servers outside your venv, so register
# the interpreter's absolute path (`mpg setup` does this automatically):
claude mcp add mpg -- "$(python -c 'import sys; print(sys.executable)')" -m modern_python_guidance mcp
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

For venv installs, set `"command"` to your interpreter's absolute path and `"args"` to `["-m", "modern_python_guidance", "mcp"]` for the same reason as above.

**Agent Skills + Rules only (Claude Code):**
```bash
mpg setup --skills-only
```

**`mpg setup` flags:**
| Flag | Purpose |
|------|---------|
| `--mcp-only` | MCP registration only |
| `--skills-only` | Project-local artifacts only (Skills + Rules) |
| `--scope {user,local}` | MCP scope (default: user) |
| `--project-dir PATH` | Target project for Skills/Rules symlinks |
| `--dry-run` | Show what would be done |
| `--no-hook` | Don't register the PostToolUse hook (removes it if already present) |
| `--with-hook` | Register the hook even if this project already has mpg artifacts |

If this project already has mpg's Skills or Rules symlinks from a previous `mpg setup`, the hook is not silently enabled — you'll see a note instead (`New: mpg can auto-check Python files after every edit.` / `Enable: mpg setup --with-hook`). A fresh project gets the hook by default.

After registering, `mpg setup` checks whether a same-name registration in a higher-precedence scope (local > project > user) would shadow the one it just wrote, and prints a warning with the exact `claude mcp remove` command if so.

**Uninstall** — reverse `mpg setup` (deregister the MCP server and unlink Agent Skills + Rules):
```bash
mpg uninstall            # remove all
mpg uninstall --dry-run  # preview what would be removed
```

| Flag | Purpose |
|------|---------|
| `--mcp-only` | MCP deregistration only |
| `--skills-only` | Project-local artifacts only (Skills + Rules) |
| `--project-dir PATH` | Target project for Skills/Rules symlinks |
| `--dry-run` | Show what would be done |

`mpg uninstall` clears the MCP registration from every scope `setup` can write to (user and local), removes only the symlinks mpg created (never their targets or other files), removes mpg's PostToolUse hook entry from `.claude/settings.local.json` (leaving any other tools' hooks untouched), and is idempotent — running it on an already-clean state is a harmless no-op.

</details>

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

# Scan a file for outdated patterns
mpg check app.py
mpg check app.py --format json | jq '.summary.guide_ids'
mpg check app.py --exit-zero  # always exit 0

# JSON output (default when piped, explicit with --format)
mpg search "typing" --format json | jq '.[0].id'

# Read dependency evidence from another project; hide proven-incompatible guides by default
mpg search "pydantic validator" --project-dir ../my-app

# Supply an exact target-environment override when files cannot prove it
mpg search "pydantic validator" --dependency-version package:pydantic=2.7.4
```

## Guide coverage

41 guides across 3 layers:

| Layer | Categories | Count | Examples |
|-------|-----------|-------|---------|
| **1 — stdlib** | typing, async, stdlib, data-structures | 18 | `list` over `List`, `match`/`case`, `TaskGroup`, deferred annotations, t-strings |
| **2 — frameworks** | pydantic, fastapi, httpx, django, sqlalchemy, pytest | 18 | Pydantic V2 migration, SQLAlchemy 2.0 style, `Annotated[Depends]` |
| **3 — toolchain** | toolchain | 5 | `uv` over `pip`, `ruff` over flake8, `pickle` avoidance |

Run `mpg list` to see all 41 guides, or [browse them on GitHub](skills/modern-python-guidance/guides/).

## Version-aware filtering

Guides specify their minimum Python version. Every guidance command resolves the target
Python from the nearest project context (and discloses the result as
`target_python: {version, source}`) using this precedence:

1. `--python-version` flag
2. `pyproject.toml` `requires-python`
3. `pyproject.toml` Poetry `python` constraint (`^3.10`, `~3.11`, `>=3.10,<3.14`)
4. `.python-version` file
5. Default: 3.11

The same resolver is used by CLI search/retrieve/list/check, the MCP guidance tools,
and the PostToolUse hook. An explicit CLI/MCP version always wins. `mpg detect-version`
keeps its plain output for scripts; use `mpg detect-version --format json` to audit the
resolved version and stable source label, including when a JSON search or list result is empty.

```bash
# Only shows guides compatible with Python 3.9 (explicit override)
mpg list --python-version 3.9
# Excludes: TaskGroup (3.11+), match/case (3.10+), etc.
```

## Dependency-aware applicability

Framework and toolchain guides declare machine-readable `applies-to-packages` and/or
`applies-to-tools` metadata. Every declared requirement must be proven (**AND**
semantics). `mpg search` and `mpg list` hide guidance that is proven
**incompatible** by default; use `--include-incompatible` to inspect it. `retrieve`
always returns an explicitly requested guide so migration work can be reviewed.

Use `--project-dir PATH` to read the nearest project evidence, and repeat
`--dependency-version KIND:NAME=VERSION` for an exact target-environment override.
The MCP `search_guides`, `retrieve_guides`, and `list_guides` tools expose the same
`project_dir` (relative to the MCP server), `dependency_versions` object, and
`include_incompatible` option where filtering applies.

Results contain additive `dependency_requirements` and `dependency_compatibility`
objects. Status is deliberately conservative:

- **confirmed**: all requirements are proven compatible;
- **incompatible**: at least one requirement is proven incompatible;
- **unknown**: evidence is absent, ambiguous, conditional, or cannot safely prove a range.

Unknown is not confirmation. Do not infer the target environment from the interpreter
running mpg, a `[tool.uv]`/`[tool.ruff]` table, optional or dependency-group entries,
or an unrooted/ambiguous lockfile. The PostToolUse hook suppresses known-incompatible
findings and asks for verification when status is unknown; `mpg check` follows the
same rule and annotates remaining unknown findings in JSON/human output.

## PostToolUse hook

`mpg setup` registers a [PostToolUse hook](https://docs.anthropic.com/en/docs/claude-code/hooks) by default (see [Quick start](#quick-start) above) — no manual `.claude/settings.local.json` editing needed. It checks every `.py` file Claude edits or writes against the full 41-guide catalog and surfaces findings via `hookSpecificOutput.additionalContext`, so Claude receives them as part of its own context rather than as a raw stderr error.

A few things worth knowing about how it behaves:

- **It scans the whole edited file, not just your diff.** An edit anywhere in a file can resurface pre-existing outdated patterns you didn't touch this time, not only the lines you just wrote.
- **Findings are capped at 5 per edit**, plus a `+N more` summary line, to bound how much context gets injected.
- **Only the guide ID and line number are surfaced — never the matching source line itself.** Echoing arbitrary file content back as an authoritative-looking hook message would be an indirect prompt-injection channel; `guide_id` + line number is enough for Claude to look up the modern form.
- The project's target Python version is auto-detected the same way as `mpg detect-version` (nearest `pyproject.toml` `requires-python` / Poetry `python` constraint, or `.python-version`, walking up from the edited file), so patterns that require a newer Python than your project targets are not flagged. The resolved target and source are shown in the summary (`[target: py3.X; source: SOURCE]`).
- Non-Python files and clean files produce no output.
- An existing project (Skills/Rules already linked from a previous `mpg setup`) is never silently opted in — see the `--with-hook`/`--no-hook` flags above.

Verify with `/hooks` in Claude Code to confirm it's active.

For manual CLI use, `mpg check --quiet <file>` uses the same automatic resolver. Pass
`--python-version X.Y` when you intentionally want an explicit override; the JSON output
contains the same top-level `target_python` object.

<details>
<summary>Manual hook setup (advanced)</summary>

If you'd rather manage the hook entry yourself instead of `mpg setup`, add it to `.claude/settings.local.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/python",
            "args": ["-m", "modern_python_guidance", "hook", "claude-post-tool-use"]
          }
        ]
      }
    ]
  }
}
```

Use the interpreter's absolute path (`command`), not a bare `mpg`/`python` — Claude Code spawns hooks from its own environment, where a venv-only interpreter is not on PATH. `mpg setup` resolves and pins this for you automatically.

</details>

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
