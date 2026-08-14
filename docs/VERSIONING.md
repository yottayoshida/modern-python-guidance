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

Exit codes are a surface of their own — see [6](#6-exit-code-guarantees) — because what is
frozen there is a list of rows rather than everything the process can exit with.

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

### 3. JSON output fields

The field names in `search`, `retrieve`, `list`, `check`, and `detect-version` output.
**Additive only**: new fields may appear in a minor release; existing ones may not be
removed or renamed.

Which side of each is actually read back differs, and the difference is worth stating:

| Output | CLI | MCP |
|---|---|---|
| `search` | held | held |
| `list` | held | held |
| `detect-version` | held | held |
| `retrieve` | held | **not compared against design.md** |
| `check` | held | **no such tool exists** |

`retrieve_guides` shares `retrieve()` with the CLI but builds `target_python` and the
not-found envelope itself, so a field could be dropped on the MCP side alone. Its tests
check particular values rather than the field set. `check` has no MCP tool at all — the
server exposes `search_guides`, `retrieve_guides`, `list_guides`, and
`detect_python_version` — so "the CLI and the MCP tools" said of all five would name a
surface that does not exist.

Held by two helpers in `tests/conftest.py`, reading the schema examples in
[design.md](design.md) and comparing them against real output. They are not equally strong,
and the difference is worth stating rather than smoothing over:

- `search`, `retrieve`, and `list` are held by `extract_design_md_keys`, which compares
  **top-level names** and does so as a subset — the documented names must appear in the
  output. Deleting a field from design.md shrinks the documented set and still passes, so
  this direction holds the serializer to the document but not the document to the
  serializer, and nested objects go unread.
- `check` and `detect-version` are held by `design_md_field_paths`, which compares the
  **whole recursive path set** with `==`. `target_python.source` and
  `matches[].dependency_compatibility.status` are covered, and a field added to either side
  alone fails.

The weaker direction is the older one and is tracked for repair; naming it here is cheaper
than discovering later that "held" meant two different things.

The `source` values in `detect-version` output are a fixed vocabulary, not free text, so
that list is frozen too: `tests/test_version_detect.py` compares design.md's list against
`PythonVersionSource` and separately runs one input per label, because a `Literal` nothing
enforces at runtime would otherwise let a documented label exist that no input produces.

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

### 6. Exit-code guarantees

The rows of the exit-code table in [design.md](design.md) — a command, a condition a caller
can produce, and the status it exits with. **The rows, not exit-code semantics in general.**

Held by `tests/test_exit_code_contract.py`, which parses the table, checks that every row
has a scenario measuring it, and runs each one.

The narrower wording is the honest one. Comparing the table against a set of scenarios shows
that the document and the tests agree; it cannot show that no other exit exists. Reading the
exits out of the source instead would not help: `setup` and `uninstall` exit with a variable,
argparse produces exits of its own, and a signal never reaches the interpreter — a scan would
miss all three and could not report that it had. So the promise covers the enumerated rows,
and what falls outside is written beside the table: exits argparse generates, termination by
signal (a closed pipe kills the process rather than raising `BrokenPipeError` — a shell
reports 141, a parent reading the raw status sees `-SIGPIPE`), uncaught exceptions, and
`hook` — whose status belongs to surface 5 above and is held there.

**Adding a row is not automatically safe.** Unlike a new JSON field, which an old client
ignores, a new exit condition can change what an existing input returns. New conditions are
judged on whether they move an existing case, not waved through as additive.

Two rows use a fixture that matches a `check` detector, so they depend on the catalog, which
is not frozen. Retiring that guide means changing the test input — not the guarantee.

## Not frozen

- **The Python import API** (`from modern_python_guidance import ...`). This package is a
  CLI and an MCP server; its module layout is an implementation detail and moves with
  refactoring. Importing from it is not supported.
- **The guide catalog.** Guides are content: added, revised, and occasionally retired. The
  count is not a promise, and neither are the ids — though `retrieve` selects by them, so
  renaming one breaks anyone scripting against it. Such a change is recorded in the
  CHANGELOG rather than silently made.
- **Exits outside the table in surface 6**: the ones argparse generates, termination by
  signal, and uncaught exceptions. Excluded because nothing can compare them against a
  documented shape, which is the same reason `check` and `detect-version` output and
  exit codes were all excluded until [#224](https://github.com/yottayoshida/modern-python-guidance/issues/224)
  gave them holders. Widening a freeze is not a breaking change, so the order stays
  hold-then-declare: every surface named above has a holder today.
- **The JSON value types.** Field names are frozen; whether `total_matches` is an integer
  or an array is not compared. A caller depending on the types is depending on something
  no test holds.

## Deprecation

Anything removed from a frozen surface is deprecated first: it keeps working, says so when
used, and the CHANGELOG names the replacement. Removal happens no earlier than the next
major version. A deprecation that has not appeared in at least one release does not count
as notice.
