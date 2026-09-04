# modern-python-guidance

[![CI](https://github.com/yottayoshida/modern-python-guidance/actions/workflows/ci.yml/badge.svg)](https://github.com/yottayoshida/modern-python-guidance/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/modern-python-guidance.svg)](https://pypi.org/project/modern-python-guidance/)
[![Python](https://img.shields.io/pypi/pyversions/modern-python-guidance.svg)](https://pypi.org/project/modern-python-guidance/)
[![License](https://img.shields.io/github/license/yottayoshida/modern-python-guidance.svg)](LICENSE)

Stop your AI from writing `typing.List`, `@validator`, and `setup.py`. 41 version-aware BAD/GOOD pattern guides that teach AI coding agents to write modern Python — carried by a rules file that loads whenever you edit Python or project config, a check that runs on each `.py` file you save, and MCP/CLI lookup for the rest of the catalog.

## Highlights

- **Evidence status**: Historical V5 content-efficacy evidence is documented with its model, prompt, sample, metric, and delivery scope; it is not a product-wide effectiveness claim ([V5 benchmark details](docs/benchmark-v5.md))
- **41 guides** across stdlib, Pydantic, FastAPI, Django, SQLAlchemy, pytest, and toolchain
- **Version- and dependency-aware**: filters Python-version-incompatible guidance and qualifies framework/tool guidance from project evidence
- **Delivery, in the order it reaches you**: a Rules file auto-loaded when you edit Python files *or* project config (`pyproject.toml`, `requirements*.txt`, `setup.cfg`, `.python-version`, `Pipfile`) — this is the path carrying the embedded patterns; a PostToolUse hook checking each saved `.py`; Agent Skills; and MCP/CLI lookup for the rest of the catalog
- **Not Ruff**: Ruff auto-fixes syntax (`List` → `list`). mpg guides design decisions that Ruff can't touch — `TaskGroup` over `gather`, Pydantic V2 migration, SQLAlchemy 2.0 style

<!-- mpg-benchmark-claims:start -->
Benchmark evidence status: historical V5 cells remain documented for audit, but no traceable numeric product claim is currently promoted. Default `mpg setup` end-to-end effectiveness has not yet been measured.
<!-- mpg-benchmark-claims:end -->

> **Note:** The tool itself requires Python 3.11+ to run. Guides cover patterns from Python 3.9 onward, and `--python-version` filters guides for your target environment.

## Quick start

### Claude Code (recommended)

```bash
pip install modern-python-guidance
mpg setup
```

This registers the MCP server, links Agent Skills, creates a Rules file (`.claude/rules/modern-python.md`), and registers a PostToolUse hook in one command. The Rules file auto-injects modern Python guidance whenever you touch Python-related files, and the hook checks each edited `.py` file against the guides with a detector applicable to the target project (see [PostToolUse hook](#posttooluse-hook) below). Advisory-only gaps are disclosed through CLI/MCP metadata. Start a new Claude Code session afterwards — newly registered MCP servers, skills, rules, and hooks take effect on the next launch.

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
| `--project-dir PATH` | Target project for local MCP and project artifacts |
| `--dry-run` | Show what would be done |
| `--no-hook` | Don't register the PostToolUse hook (removes it if already present) |
| `--with-hook` | Register the hook even if this project already has mpg artifacts |

If this project already has mpg's Skills or Rules symlinks from a previous `mpg setup`, the hook is not silently enabled — you'll see a note instead (`New: mpg can auto-check Python files after every edit.` / `Enable: mpg setup --with-hook`). A fresh project gets the hook by default.

After registering, `mpg setup` checks whether a same-name registration in a higher-precedence scope (local > project > user) would shadow the one it just wrote, and prints a warning with the exact `claude mcp remove` command if so.

When `mpg setup` reports success, every symlink it created leads to a bundled source with readable content — a skills directory carrying a readable `SKILL.md`, and a non-empty rule file. An installation that is present but hollow (a packaging or install accident) fails setup with the hollow path named, instead of linking silently; `mpg doctor` keeps reporting an already-made link to such a source as `degraded`, exactly as described under **Check the install** below.

**Uninstall** — reverse `mpg setup` (deregister the MCP server and unlink Agent Skills + Rules):
```bash
mpg uninstall            # remove all
mpg uninstall --dry-run  # preview what would be removed
```

| Flag | Purpose |
|------|---------|
| `--mcp-only` | MCP deregistration only |
| `--skills-only` | Project-local artifacts only (Skills + Rules) |
| `--project-dir PATH` | Target project for local MCP and project artifacts |
| `--dry-run` | Show what would be done |

`mpg uninstall` clears the MCP registration from every scope `setup` can write to (user and local), removes only the symlinks mpg created (never their targets or other files), removes mpg's PostToolUse hook entry from `.claude/settings.local.json` (leaving any other tools' hooks untouched), and is idempotent — running it on an already-clean state is a harmless no-op.

When `--scope local` is used, `--project-dir` is also the cwd for every MCP add, replacement, health-check, and removal operation. A missing target is created before local setup; uninstall fails closed for a missing explicit target instead of touching the caller's local registration. User-scope MCP operations remain global and do not use this path.

**Check the install** — `mpg doctor` reports what each delivery channel is actually doing. It repairs nothing; `mpg setup` remains the repair tool.

```bash
mpg doctor                        # inspect the nearest project root
mpg doctor --project-dir ./app    # inspect a specific project
```

Each channel reads as `present`, `degraded`, `absent`, or `unknown`, with the fix printed beside anything broken. The exit status is the machine-readable half: **0** when every channel is present or absent, **1** when any is degraded, **2** when any could not be determined. `absent` is not a failure — `--mcp-only`, `--skills-only`, and `--no-hook` each make it a configuration someone chose. `unknown` is never folded into health, because a check that cannot tell "working" from "not measured" is not a check.

`present` means the delivery path is intact and carries something. For the Skills and Rules symlinks that means the target is opened and read, not just named — a link whose destination has the right name and nothing behind it is `degraded`. For the hook it means the registration is the shape Claude Code runs: the entry is a `command` entry, its arguments are the ones that invoke mpg, and exactly one entry matches each of the tools mpg hooks. A registration that only matches other tools never fires on an edit, and two that match the same tool are one more than `mpg setup` writes; both read as `degraded`. Every mpg entry in the file is examined, not the first one found.

A matcher written as a regular expression is answered only from a subset measured to mean the same thing in both engines. Claude Code evaluates that form in JavaScript and `doctor` evaluates it in Python, and the two languages differ at the edges — `(?P<x>Edit)|Write` fires in Python and is a syntax error in JavaScript, so the hook never runs while the old check called it `present`. The subset, and what was measured to draw it, are in `matcher_fires_on`'s docstring; anything outside it, including working patterns like `(Edit|Write)` or `\d`, reads as `unknown` rather than being answered from the wrong engine. The simple form (`Edit|Write`, `Edit, Write`) is unaffected, and is not covered by that measurement either: `doctor` answers it by splitting on `|` and `,` and comparing names, following the documented rule rather than anything measured about how Claude Code reads it.

By default the hook channel never runs the registered command, and reports only the shape of the registration. The interpreter path in a settings file is an arbitrary string, so executing it turns a read-only diagnostic into a way to run whatever a settings file names — including one that arrived with a repository you cloned. The cost of not running it is that an interpreter which exists but no longer has mpg installed reads as `present`, since nothing has asked it.

`mpg doctor --run-interpreter` asks it. The registered interpreter is run the way Claude Code spawns the hook — `<command> -m modern_python_guidance --version` — and the channel is `present` only if that prints mpg's name and a version. An exit status of 0 is not enough: a program that ignores its arguments and succeeds satisfies one without loading anything. Any version is accepted, not this installation's, because a hook wired to an interpreter holding an older mpg is working. A non-zero exit, or output that is not a version line, is `degraded`; an interpreter that cannot be started at all (a missing shebang target, no execute permission) is `degraded` too, since Claude Code spawning the same hook meets the same wall. A timeout, a failure to start for reasons of this process's own, or more than four distinct interpreters to try, read as `unknown`.

The run is bounded: no stdin, at most four kilobytes of output read, five seconds per interpreter, its own process group killed on timeout, an environment holding only `PATH` and `HOME`, a scratch working directory, and at most four distinct spellings of a command per run — so about twenty-five seconds in the worst case, and `../python` counts separately from `python`.

**Those bounds cap the damage; they do not prevent it.** A child that calls `setsid()` outlives the group kill and keeps running after `doctor` has answered. Nothing stops it reaching the network. It runs as you, so everything you can read it can read — `~/.aws/credentials` included — and everything you can write it can write, which is the more durable problem: five seconds is enough to append to `~/.zshrc`. `PATH` and `HOME` are there because a pyenv or conda shim cannot start without them, and dropping the rest is what keeps credentials held in the environment out of reach; it does nothing about credentials in files.

Opting in is the actual control, which is why this is a flag you type rather than a default. **Do not put `--run-interpreter` in CI**: a fork's pull request can carry both a binary and the settings file naming it, and a checkout path in CI is predictable.

Two things it does not establish. That the hook produces guidance — `present` here means something printed a version line, no more, and a program that only echoes one satisfies it. And that a slow machine will finish in five seconds: exceeding the timeout on a healthy interpreter reads as `unknown`, which exits 2.

Inspecting the MCP registration runs `claude mcp get`, which starts the server to answer, so `mpg doctor` takes roughly 1.5 seconds rather than being instant. That is also why it does not use `claude mcp list` — that connects to every server you have configured, and took 30 seconds on the machine this was measured on.

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

# Filter by layer (1 stdlib, 2 frameworks, 3 toolchain) or by how often the pattern is missed
mpg list --layer 2
mpg list --frequency high

# Filters combine — this is the intersection, not the union
mpg list --layer 1 --frequency high

# Emit the selected guides with their full bodies, for building a system prompt
mpg list --layer 2 --frequency high --with-content --format json > guidance.json

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

## Supported platforms

Linux is what CI runs — `ubuntu-latest` across Python 3.11, 3.12, 3.13, and 3.14 — and macOS is where the project is developed. Both are exercised routinely.

Windows is untested, and one part of it is known to fail. `mpg setup` installs the Agent Skills directory and the rule file as symlinks, and Windows grants that privilege only with Developer Mode enabled or from an elevated prompt; without either, `os.symlink` raises `WinError 1314` and those two steps report an error. The remaining steps are unaffected — MCP registration and hook registration run independently and complete — but `mpg setup` still exits non-zero, because one of its steps failed. `mpg setup --mcp-only` avoids the symlinks entirely, at the cost of skipping the hook as well. This is read off the code path, not observed: no Windows machine has run it.

## Guide coverage

41 guides across 3 layers:

| Layer | Categories | Count | Examples |
|-------|-----------|-------|---------|
| **1 — stdlib** | typing, async, stdlib, data-structures | 18 | `list` over `List`, `match`/`case`, `TaskGroup`, deferred annotations, t-strings |
| **2 — frameworks** | pydantic, fastapi, httpx, django, sqlalchemy, pytest | 18 | Pydantic V2 migration, SQLAlchemy 2.0 style, `Annotated[Depends]` |
| **3 — toolchain** | toolchain | 5 | `uv` over `pip`, `ruff` over flake8, `pickle` avoidance |

Run `mpg list` to see the 41-guide catalog, or [browse it on GitHub](skills/modern-python-guidance/guides/).

## Selecting a subset of the catalog

`--category`, `--layer`, and `--frequency` select on guide metadata and combine as an
intersection: `--layer 1 --frequency high` returns the guides that are both, not either.
`search` and `list` accept all three, as do the `search_guides` and `list_guides` MCP tools.
`mpg list --with-content` adds each guide's full body to the output, which is the shape to
pipe into a system prompt or a generated rules file.

Two things to expect. First, the counts you get back are what survives *after* the target
Python and dependency filters, which apply on every command whether or not you asked for
them — `mpg list --layer 1` reports fewer guides than the layer table above when your
project targets an older Python, and `--python-version 3.14` shows the full catalog.
Second, `mpg search` falls back to fuzzy suggestions whenever the exact query matches
nothing, and a filter can leave it with nothing to match; a precise query that returns
unexpected results marked `fuzzy: true` usually means the filter excluded the guide you
were looking for, not that the query was wrong.

Note that `--layer` and `--frequency` make two abbreviations ambiguous that used to resolve:
`--f` no longer selects `--format`, and `--l` no longer selects `--limit`. Spell those two out.

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
`include_incompatible` option where filtering applies. `search_guides` and `list_guides`
additionally accept `layer` and `frequency`; `retrieve_guides` takes neither, since it is
addressed by explicit ID.

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

`mpg setup` registers a [PostToolUse hook](https://docs.anthropic.com/en/docs/claude-code/hooks) by default (see [Quick start](#quick-start) above) — no manual `.claude/settings.local.json` editing needed. It checks every `.py` file Claude edits or writes against the detector-capable guides applicable to the target project and surfaces findings via `hookSpecificOutput.additionalContext`, so Claude receives them as part of its own context rather than as a raw stderr error.

<!-- mpg-check-coverage:start -->
`mpg check` and the PostToolUse hook automatically check only guides with a detector for the target Python/dependency context. The current catalog has 26 detectable guides out of 41; 15 are advisory-only and are not claimed as actively checked.
Advisory-only guides: `dataclass-modern`, `dict-merge-operator`, `django-check-constraints`, `exception-groups`, `fastapi-typed-state`, `httpx-streaming`, `match-case-patterns`, `override-decorator`, `pytest-parametrize`, `pytest-raises-match`, `removeprefix-removesuffix`, `ruff-over-flake8`, `sqlalchemy-async-session`, `template-strings`, `uv-over-pip`.
A clean automatic check does not certify advisory-only guidance. Use `mpg list --format json` or MCP metadata to inspect each guide's detection status.
<!-- mpg-check-coverage:end -->

This capability contract is distinct from [#152](https://github.com/yottayoshida/modern-python-guidance/issues/152): #181 describes which guides can produce automatic findings after activation, while #152 measures whether an organic development session reaches the catalog at all.

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

## Versioning

Semantic Versioning. From 1.0 onward the CLI surface, the MCP tool schemas, the JSON output fields, the guide frontmatter schema, the PostToolUse hook contract, and the documented exit-code rows are frozen. [docs/VERSIONING.md](docs/VERSIONING.md) says what each of those covers, what holds it in place, and what is deliberately left outside the freeze — including which side of each JSON surface is actually compared, and why exit codes are frozen row by row rather than as semantics in general.

## License

Apache-2.0 OR MIT — see [LICENSE](LICENSE) and [LICENSE-MIT](LICENSE-MIT).
