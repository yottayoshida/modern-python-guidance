# Versioning and compatibility

modern-python-guidance follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

From 1.0 onward, the surfaces below are frozen: removing from them, renaming within them,
or changing what they mean requires a major version. Anything not listed may change in a
minor release.

Each surface states what holds it in place. A frozen surface that nothing reads back is a
failure this project has already made — the `Typing :: Typed` classifier shipped false for
35 releases because no test looked at it ([#204](https://github.com/yottayoshida/modern-python-guidance/issues/204)).

## Frozen surfaces

### 1. CLI surface

Command names, their positional arguments, and their option names.

```
check  detect-version  hook  list  mcp  retrieve  search  setup  uninstall
```

Held by `tests/test_versioning_contract.py`: the list above is compared against
`cli.COMMAND_GROUPS` — the same table that registers the subparsers and renders
`mpg --help` — and each command's positionals and options are compared against what
`build_parser()` produces. `-h` and `--help` belong to argparse and are not part of this.

**Exit codes are not frozen.** They are documented under "Output format" in
[design.md](design.md), and `tests/test_cli_integration.py` asserts particular ones, but
nothing compares the documented semantics against the implementation as a whole. Freezing
them here would be a promise with no holder.

### 2. MCP tool schemas

Tool names and their complete input schemas — property names, types, enums, bounds,
defaults, and which properties are required.

```
search_guides  retrieve_guides  list_guides  detect_python_version
```

Held by the same test file, which compares each tool's whole `inputSchema` against a
snapshot in `tests/fixtures/frozen_mcp_schemas.json`. Comparing parameter names alone
would pass a `layer` that changed from integer to string, an enum that lost a value, or a
`limit.maximum` cut from 50 to 5 — each visible to a client and each breaking.

**One field is deliberately outside the freeze.** `maxItems` on `retrieve_guides` is
derived from the catalog size at runtime (`_guide_limit()`), so it moves whenever a guide
is added or retired. Freezing it would freeze the catalog. It is stripped before the
comparison, and a control test fails if the stripping ever stops working — otherwise the
exclusion could quietly widen.

### 3. JSON output field sets

The field names in `search`, `retrieve`, and `list` output, on both the CLI
(`--format json`) and the MCP tools. **Additive only**: new fields may appear in a minor
release; existing ones may not be removed or renamed.

Held by `tests/conftest.py::extract_design_md_keys`, which reads the schema examples in
[design.md](design.md) and compares them against real output.

**`check` and `detect-version` output are not covered.** design.md documents a schema for
`check`, but `extract_design_md_keys` reads only the three sections above; `detect-version`
has no documented schema at all. Listing them here would name a surface with nothing
comparing it — the failure this document opens by citing.

### 4. Guide frontmatter schema

The required fields, and the `layer` and `frequency` vocabularies that contributed guides
are parsed against.

Held by `frontmatter.py`: `REQUIRED_FIELDS`, `VALID_LAYERS`, and `VALID_FREQUENCIES` are
enforced at parse time, so a guide violating them fails to load rather than loading with
surprising semantics.

### 5. PostToolUse hook stdout contract

The `hookSpecificOutput.additionalContext` shape written to stdout, and the exit code
that accompanies it.

Held by `tests/test_cli_unit.py`, which reads the emitted JSON rather than the exit status
alone — a hook that exits 0 while printing nothing usable is the failure mode this
contract exists to prevent.

## Not frozen

- **The Python import API** (`from modern_python_guidance import ...`). This package is a
  CLI and an MCP server; its module layout is an implementation detail and moves with
  refactoring. Importing from it is not supported.
- **The guide catalog.** Guides are content: added, revised, and occasionally retired. The
  count is not a promise, and neither are the ids — though `retrieve` selects by them, so
  renaming one breaks anyone scripting against it. Such a change is recorded in the
  CHANGELOG rather than silently made.
- **`check` and `detect-version` JSON output, and exit-code semantics.** Left out for one
  reason only: nothing currently compares them against a documented shape. Widening a
  freeze is not a breaking change, so the order was hold-then-declare — every surface
  named above has a holder today, rather than five named and three held. Tracked in
  [#224](https://github.com/yottayoshida/modern-python-guidance/issues/224).

## Deprecation

Anything removed from a frozen surface is deprecated first: it keeps working, says so when
used, and the CHANGELOG names the replacement. Removal happens no earlier than the next
major version. A deprecation that has not appeared in at least one release does not count
as notice.
