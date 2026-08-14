# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). What a version number promises — which surfaces are frozen and what holds each one — is set out in [docs/VERSIONING.md](docs/VERSIONING.md).

## [Unreleased]

### Added

- The three surfaces 1.0 left out of the freeze now have something holding them, and are frozen: `check --format json`, `detect-version --format json` (with the MCP tool `detect_python_version`), and exit codes. They were excluded for one reason — nothing compared them against a documented shape — and the fix had to start with the comparison rather than the declaration. `check` and `detect-version` are held by a recursive field-path comparison against the examples in design.md, using `==` rather than the `<=` the three existing JSON surfaces use. That direction matters: deleting a field from design.md shrinks the documented set, and a smaller subset still fits, so the older comparisons hold the serializer to the document but not the document to the serializer — measured, not assumed. Walking the whole value rather than the top-level names is what puts `target_python.source` and `matches[].dependency_compatibility.status` under the freeze; a comparison of outermost keys would let either vanish. The `source` labels are frozen as a vocabulary too, compared against `PythonVersionSource` from the schema section alone — the precedence section already lists all five, so a file-wide search would have reported agreement no matter what the schema section said — and separately checked by running one input per label, because a `Literal` enforces nothing at runtime and a documented label no input produces would otherwise pass. Exit codes are frozen as **the rows of a table**, not as semantics in general. Comparing a table against a set of scenarios shows the document and the tests agree; it cannot show no other exit exists, and reading the exits out of the source would not help either, since `setup` and `uninstall` exit with a variable, argparse produces its own, and a signal never reaches the interpreter. What falls outside is written beside the table: argparse's exits, termination by signal, uncaught exceptions, and `hook`, whose status the PostToolUse contract already holds. `BrokenPipeError → 0` is not among the guarantees — `main()` restores the default `SIGPIPE` disposition, so a closed pipe terminates the process by signal (141 as a shell reports it, `-SIGPIPE` in a parent reading the raw status) and the `except` clause is not what a caller observes. Adding an exit condition is not treated as additive the way a new JSON field is: an old client ignores a field, but a new condition can change what an existing input returns. (closes #224)

### Changed

- design.md's rule that the CLI "defaults to JSON when piped" now names its exception. `detect-version` takes `--format json|plain` rather than `json|human` and defaults to `plain` whether or not a pipe is attached, because the plain version string is what scripts read. The behaviour is unchanged; what changes is that the general rule no longer contradicts it — freezing the surface while the document described it wrongly would have frozen the contradiction.

## [1.0.0] — 2026-08-11

**Summary**: 1.0 states what the version number promises. `docs/VERSIONING.md` names five frozen surfaces — the CLI, the MCP tool schemas, the JSON output field sets, the guide frontmatter schema, and the PostToolUse hook stdout contract — and, for each, the test that holds it. Reaching that point meant repairing what the packaging had been claiming falsely: the `Typing :: Typed` classifier had shipped for 35 releases without its PEP 561 marker, no platform was declared anywhere, and four `frequency: high` guides reached no session at all because their only route was a catalog that measurement found unused. Nothing here changes the CLI or the MCP surface for existing callers; what changes is that those surfaces are now promises with something behind them.

### Added

- `docs/VERSIONING.md` states what a version number promises. Five surfaces are frozen from 1.0 onward — the CLI surface, the MCP tool schemas, the JSON output field sets (additive only), the guide frontmatter schema, and the PostToolUse hook stdout contract — and each names what holds it in place, because a frozen surface nothing reads back is the failure this project already made with `Typing :: Typed`. Three were held already: by the design.md schema comparison, by the hook's stdout tests, and by the frontmatter parser refusing violations. The CLI surface and the MCP schemas were not, and each gained a test — command names, positionals and option names read back from `build_parser()`, and every tool's whole `inputSchema` compared against a snapshot, so a `layer` changing from integer to string or a `limit.maximum` cut from 50 to 5 fails rather than slipping past a comparison of parameter names. Three things are deliberately outside the freeze because nothing compares them today: `check` and `detect-version` JSON output, and exit-code semantics; naming them would have made the document's own claim false in its opening paragraph, and widening a freeze later is not a breaking change. `maxItems` is excluded for a different reason — derived from the catalog size, so freezing it would freeze the catalog — with a control test pinning the premise of that exclusion. The Python import API and the guide catalog are named as not frozen, ids included, since `retrieve` selects by them and a rename is a breaking change recorded here rather than made quietly. (closes #203)

### Changed

- The `Development Status` classifier moved from `3 - Alpha` to `4 - Beta`, which 35 tagged releases, a four-version CI matrix and a 92% coverage gate already described; a release that self-describes as Alpha contradicts itself on its own PyPI page. A test now derives the required value from the version in `pyproject.toml`, so the eventual bump to 1.0 cannot land while the classifier still says Beta. Prereleases of 1.0 are exempt, since `1.0.0rc1` is where a project finds out whether it is stable and requiring the stable classifier there would force the claim ahead of the evidence. The issue asked for a line item in a v1.0 release checklist; no such checklist exists in this repository, and a test fires in the same commit as the version bump, which a checklist line can be skipped in. (closes #207)

### Removed

- `docs/superpowers/` and the two planning documents inside it. They were the plan and design used to file five issues on 2026-08-06; those issues were filed, implemented in #184–#189, and closed, and the spec's text is the issue bodies verbatim — #179 and its siblings carry it, so removing the drafts loses nothing the project relies on. No document in the repository referenced the directory, it never reached the wheel, and the plan opened with an instruction addressed to whatever agent read it next, which a public repository has no reason to keep offering. Recover with `git log --all --full-history -- docs/superpowers/`. (closes #217)

### Fixed

- Four `frequency: high` guides now reach a session. `dataclass-modern`, `pytest-parametrize`, `ruff-over-flake8`, and `uv-over-pip` had no detector — so the hook could never surface them — and no entry in the embedded-patterns section, which left the MCP catalog as their only route, and #152 measured that route as unused. All four are now carried by the Rules file, which loads on Python files *and* on project config (`pyproject.toml`, `requirements*.txt`, `setup.cfg`, `.python-version`, `Pipfile`), so the two toolchain guides arrive exactly when their own trigger files are being edited. The always-loaded body grew from 674 to 771 tokens; that is paid on every matching edit, which is why the routes were recorded on the issue before implementation. Adding detectors was considered and rejected: the guides present `frozen`/`slots`/`kw_only` as decisions rather than corrections, so an automatic finding would fire on correct mutable dataclasses. Each embedded line is now checked against the wording of its own guide, after a draft recommended `uv sync` — a command `uv-over-pip` never mentions, and whose GOOD section keeps `uv pip install -r requirements.txt` rather than asking anyone to abandon `requirements.txt`. (closes #208)

- The README no longer leaves out the delivery path that actually works. Its first line offered "MCP, CLI, or Agent Skills" without naming the Rules file, and the Highlights entry said Rules auto-inject on `.py` file touch — both inaccurate, since Rules also load on project config and a scan of session logs found the MCP catalog essentially unused. The ordering now follows what reaches a session first, and a test ties the claim to `RULE_FRONTMATTER` so the prose cannot drift from the paths again. `search_guides` had its own version of the problem: its description told agents to search for anything outside "~5" embedded patterns and named pytest as an example, which this change made false in the same commit that moved pytest into the rules body. (closes #152)

- The Python versions the classifiers advertise are now checked, and against two different facts because they answer to two. The lowest must agree with `requires-python` in both directions — those two tell installers the same thing or one of them is wrong. The set must be a subset of what CI tests, in one direction only: `Programming Language :: Python :: 3.14` has been in `pyproject.toml` since the initial scaffolding while CI gained 3.14 in #105, a PR that changed `ci.yml` alone, so equality would have made every commit before that one a violation and would forbid trying a Python in CI before committing to support it. `Environment :: Console` is checked in the same one direction: the claim requires a console script, a script does not require the claim. Reading the CI matrix needs no new dependency — the pattern is scoped to `matrix:` and to the `test` job, and it raises rather than comparing against an empty set when it cannot find the list, since that is the failure that reports agreement exactly when the check has lost its footing. The floor is derived by asking the specifier which minors it admits rather than by reading its written bounds, because `>=3.11,>=3.12` has two and only the higher one is real. License classifiers are deliberately left alone: #213 proposes dropping them as deprecated under PEP 639, and a test defending something slated for removal points the wrong way. (closes #220)

- CONTRIBUTING no longer states a test count or a guide count. The suite count was stale by a factor of three, so a contributor checking their environment against it would read a third of the suite failing to collect as a healthy setup. Pinning the numbers with tests was the alternative and was rejected: the guide count already has three places checking it against the catalog, and a fourth would be the duplication #219 removed. The one number kept is the dependency audit's, which says "as of" and means it. (closes #216)

- The package ships the PEP 561 marker that its `Typing :: Typed` classifier has been promising since the first release. Without `py.typed`, mypy and pyright treat an installed package as untyped no matter how annotated its source is, so every consumer silently lost the type information the classifier advertised — and the published wheel, downloaded and inspected, contained no marker at any path. The wheel verification now asserts the marker against the installed package rather than against the checkout, since the source tree holding the file proves nothing about what was packaged; the check was falsified by hand, because it runs only in the build job where a green result would otherwise be its own first evidence. (closes #204)

- The supported platforms are stated, and `mpg setup` explains itself when Windows refuses to create a symlink. No platform was declared anywhere before: no `Operating System` classifier, no mention in README, and CI running Linux alone. Both classifiers and a README section now name the two platforms with evidence behind them — Linux from CI, macOS from development — and Windows is deliberately absent from the metadata while README states what fails there and why. `os.symlink` raises `WinError 1314` on Windows without Developer Mode or elevation, and the bare error text read like a defect in mpg rather than a privilege the OS withholds, leaving two of the advertised delivery methods missing with no indication of what to change. The new hint is scoped to that error rather than to the platform, because Windows also raises `OSError` here for path lengths and read-only volumes, and answering those with a privileges setting would send the reader after a fix that does not apply. Whether to fall back to copying on Windows is left open. (closes #206)

## [0.6.0] — 2026-08-09

**Summary**: The catalog can now be sliced the way its metadata always allowed: `--layer` and `--frequency` filter `search` and `list` on both the CLI and MCP surfaces, and `mpg list --with-content` emits the selected guides in full — the shape to pipe into a generated system prompt. `mpg --help` groups the nine commands by purpose and shows runnable examples. A contributor's first commands now work as documented: `ruff check .` passes from the repository root, and an ordinary session no longer leaves the working tree dirty. One behavioural cost is recorded under Changed: the new option names make the `--f` and `--l` abbreviations ambiguous.

### Added

- `search` and `list` accept `--layer` and `--frequency`, and the `search_guides` / `list_guides` MCP tools accept the same two arguments. Filters are conjunctive, so `--layer 1 --frequency high` returns the intersection. `retrieve` is unchanged on both surfaces: it selects by explicit ID, and `docs/design.md` says so in two places. (closes #30, #31)
- `mpg list --with-content` emits each selected guide's full body alongside its metadata, which is the shape to pipe into a generated system prompt or rules file. This is where bulk retrieval belongs — the requested `retrieve --all` would have made `retrieve` a selection command and contradicted the documented guarantee that it preserves explicitly requested IDs. The body is the same one `retrieve` serves, and the field is absent unless the flag is passed, so the default `list` schema is unchanged. (closes #29)
- `mpg --help` groups the commands by what they are for and shows four runnable examples, instead of listing nine flat with no indication of how to invoke them. The grouping is composed by hand because argparse has no notion of it; the same table registers the subparsers, so a command cannot appear in the listing without existing, and adding one to the listing without wiring it up is now rejected rather than silently exiting 0. Tests compare the rendered help against the parser's own commands and parse every example shown, so a listing that drifts from the CLI fails rather than misleading. (closes #36)

### Changed

- Adding `--layer` and `--frequency` made two option abbreviations ambiguous that previously resolved: `--f` no longer selects `--format`, and `--l` no longer selects `--limit`, on both `search` and `list`. `argparse` accepts unambiguous prefixes by default, and the new options collide with the old ones; both now exit 2 with `ambiguous option`. Nothing inside this repository used the short forms, but a script that did will need them spelled out. Turning prefix matching off entirely would break every other abbreviation, so the behaviour stands and is documented instead.

### Fixed

- `ruff check .` from the repository root passes. It reported 34 violations, all of them in `bench/fixtures`, where outdated patterns are the point — so a contributor following the obvious command met a wall of failures that were never theirs to fix. Those fixtures are now excluded, and only those: the runner and scorers elsewhere under `bench/` are still linted, which a test verifies by reading back the file list ruff says it will check. Excluding `bench/` wholesale would have been shorter and would have quietly dropped the tooling too. CONTRIBUTING states the scope CI uses rather than leaving the two commands to disagree. (closes #123)

- `.coverage`, `uv.lock`, and the paths `mpg setup` writes under `.claude/` are now ignored, so an ordinary development session no longer leaves a dirty working tree. `uv.lock` is ignored rather than tracked because CI installs with `uv pip install --system -e` and never reads a lock file, so committing one would pin nothing; the choice is recorded next to the rule rather than left implicit. The `.claude/` entries name individual paths instead of the directory: a directory-wide rule would silently swallow anything the project later decides to track there, whereas an unlisted path shows up in `git status` and gets a line added deliberately. A test asks `git check-ignore` for each path rather than grepping `.gitignore`, since a pattern being present and a path being ignored are different claims, and it pins in both directions — the generated paths stay hidden and project content stays visible. (closes #125)

- Catalog selection by category now runs through a single predicate rather than four independent implementations of the same comparison — the scored search, the fuzzy fallback, `mpg list`, and the `list_guides` MCP tool each had their own. Nothing was broken beforehand; the point is that adding two filters to four separate sites is how a filter comes to be applied on three paths and quietly ignored on the fourth, and the MCP tool was the copy easiest to overlook because its sibling `search_guides` already delegates to the shared search. The accepted values for both new filters come from the frontmatter vocabulary the parser validates against, so the CLI choices, the MCP schema, and the parser cannot drift apart. The MCP server checks them in code as well: an `enum` in `inputSchema` is advertised to the client, not enforced by the server, and without the check `layer: 99` would return an empty array — which reads as "no such guides" when it means "no such layer".

## [0.5.12] — 2026-08-09

**Summary**: Several checks reported healthy without covering what they claimed — an identifier collision made the wheel-asset gate blind rather than noisy, the MCP stdout-purity test only stayed green because it exercised one request shape, and the release checker's `permissions` block silently dropped the scope its own checkout needs. Each now establishes its coverage or fails, and a weekly dependency audit is held to the same standard. Separately, `mpg setup` and `mpg uninstall` now disclose every symlinked directory a run writes through; the traversal is unchanged and is still not confinement.

### Added

- A weekly dependency audit (`.github/workflows/audit-dependencies.yml`) runs `uv audit` over the dependencies this project actually resolves and opens an issue keyed on the advisory set — so a closed issue about old advisories cannot suppress a new one, and a repeat of the same set cannot open a duplicate. It does not run on pull requests: an advisory published against a transitive dependency has nothing to do with the change under review. The verdict is decided by `scripts/check_dependency_audit.py`, which **fails rather than reporting "nothing found"** when it cannot establish what the audit covered — a missing subcommand, an unrecognized JSON shape, or an implausibly small audited set. That guard exists because a clean verdict over the wrong corpus is exactly how this check would fail silently: while it was being designed, a bare `pip-audit` reported no vulnerabilities against its own dependencies rather than this project's. CONTRIBUTING documents how to run and triage it locally. (closes #165)

### Fixed

- The wheel-asset gate compared guide identifiers as bare filename stems, which is only correct while no two categories share one. Measured, the consequence runs the opposite way from what the issue anticipated: a collision does not make the gate noisy, it makes it blind. The expected set shrinks along with whatever the index dropped, so the two agree and the check passes — a guide missing from the shipped wheel would be reported as healthy. A guide moved between categories was invisible to it for the same reason. It now compares `(category, id)` pairs derived from the wheel's own paths, which removes the dependency on globally unique stems rather than documenting it. (closes #141)
- The scheduled Python release checker files its follow-up issues with `tier:4-extend` and `area:content` alongside `enhancement`, so automatically created work lands in the same triage as everything else instead of outside the classification scheme. A test reads the `--label` arguments specifically; matching anywhere in the workflow text would have been satisfied by the issue body, which names the same words. Duplicate detection is unchanged. (closes #160)
- The scheduled Python release checker declared only `issues: write`, and declaring `permissions` at all drops every scope not listed — including the `contents: read` its `actions/checkout` step needs. Public repositories allow the checkout regardless, which is why ten consecutive weekly runs succeeded and the omission never surfaced; it would have failed the moment this repository went private. Both scopes are now declared, and a test asserts the pair without admitting any other write scope. (closes #163)

- The MCP stdout-purity test judged pollution by recomputing the expected byte count with `json.dumps`'s default `ensure_ascii=True`, while the server serializes with `ensure_ascii=False`. Any non-ASCII character reaching stdout made the two counts diverge and failed the test with no stray output present at all — not a hypothetical, since `guide_index.py` composes BAD/GOOD summaries with a `→` and a real `search_guides` response measures 12 bytes "short" under the old comparison. The test only stayed green because it exercised `tools/list` alone. The check now judges the stream's structure directly — every line non-empty, free of surrounding whitespace, a standalone JSON-RPC object carrying a `result`/`error`/`method` body, and the stream terminated by a newline — so it no longer depends on the server's serialization settings, and the test additionally pins which response ids belong on stdout so that a well-formed but extra message is still caught. Falsification tests pin that every pollution shape the byte comparison used to catch still fails, and that a genuinely non-ASCII payload passes. (closes #173)
- `mpg setup` and `mpg uninstall` now announce, once per run before writing anything, when `.claude` is a symlink and which directory the writes actually land in. Previously the per-file guards refused a symlinked `settings.local.json` but said nothing about a symlinked `.claude` directory, so the hook settings and the Skills/Rules symlinks all silently went to the link target. The symlink is still followed — refusing would break deliberate "config lives elsewhere" layouts — so this closes the silence, not the traversal; SECURITY.md states plainly that neither the per-file checks nor this disclosure confine the `.claude` tree. `--mcp-only`, which writes nothing under `.claude`, prints nothing. (closes #170)
- The same disclosure now covers every directory a run writes through, not just `.claude`. A symlinked `.claude/skills` or `.claude/rules` was followed with no note at all — the case that motivated the boundary #170 had to document. `mpg setup` and `mpg uninstall` now walk each write target below the project root, report the outermost symlinked directory on the way, and de-duplicate: a symlinked `.claude` still yields one note covering all three targets, while `skills` and `rules` pointing at different trees yield two, because there genuinely are two destinations. The final path component is skipped — those are mpg's own symlinks, so including them would make a second `mpg setup` announce mpg's own links back. The write targets are supplied by the callers rather than duplicated in the settings module, so there is no second copy of the layout to drift, and a source scan pins that no fourth target has appeared unannounced. Traversal is still not refused, and SECURITY.md still says the disclosure is not confinement. (closes #192)

## [0.5.11] — 2026-08-06

**Summary**: Guidance delivery is now more dependable and auditable: target-Python and dependency applicability are resolved consistently across CLI, MCP, and hooks; detection and benchmark claims expose their evidence and limits; and project-scoped MCP setup and uninstall honor the requested project directory.

### Added

- Benchmark claims now have a traceability manifest and deterministic README/V5 source-table checks; historical V5 cells are not promoted to a product-wide effectiveness claim, and the five delivery paths plus the unmeasured default `mpg setup` path are documented. (#183)
- Detection coverage is now explicit and machine-verifiable: CLI/MCP guide metadata reports `detectable` versus `advisory-only` methods, and `mpg check`/finding-bearing PostToolUse output discloses target-specific scope without changing clean/quiet silence. README and design docs no longer describe advisory-only guides as actively checked. (closes #181)
- Automatic target-Python resolution is now shared by CLI, MCP, `check`, and the PostToolUse hook. Search/list filter from the nearest project configuration, retrieve reports `version_match`, every non-empty guidance result discloses `target_python` provenance, and `detect-version --format json` provides an audit path for empty results. Explicit CLI/MCP overrides remain highest precedence. (closes #180)
- Dependency-aware applicability for framework and toolchain guides: package/tool requirements are machine-readable metadata with AND semantics, assessed as `confirmed`, `incompatible`, or `unknown` from bounded project evidence. `search`/`list` hide only known-incompatible guidance by default; CLI/MCP overrides and additive JSON evidence/status fields make the decision inspectable. `check` and the PostToolUse hook suppress known-incompatible findings and qualify unknown ones. (closes #179)
- `mpg setup` now registers a PostToolUse hook by default, closing the gap where MCP guides were never consulted during real Python development (0 calls across 894 `.py` edits). An existing project (Skills/Rules already present) gets an announcement instead of a silent behavior change unless `--with-hook` is passed; `--no-hook` actively removes an existing registration. (#152)
- Hook output switches from exit 2/stderr to exit 0 + `hookSpecificOutput.additionalContext`, carrying more compliance weight with Claude; raw source lines are no longer echoed (only `guide_id` + line number), narrowing the indirect-prompt-injection surface a full source excerpt would open.
- Rules file, SKILL.md, and the `search_guides` MCP tool description now include a proactive nudge to consult the full 41-guide catalog when writing Python outside the 5 embedded high-frequency patterns. (#152)
- `bench/run-v6.sh` + `bench/score_v6.py`: a new benchmark harness measuring whether an organic, multi-turn `.py`-editing session that never mentions mpg/MCP by name actually reaches the guide catalog (real MCP `tool_use`/CLI invocations, not grep-over-text), stratified by guidance condition (none / rules+skills+MCP / +hook). Validated end-to-end with a single live PoC session; the full measurement campaign is a separate, cost-approved follow-up. (#152)

### Fixed

- `mpg setup --scope local --project-dir X` now creates `X` before registering the local MCP server, including `--mcp-only`; dry-run previews the target without creating it, and user-scope registration remains global. (#167)
- `mpg uninstall --project-dir X` now removes local MCP registration from `X` while keeping user-scope removal global. If an explicit target is missing, local cleanup fails closed instead of falling back to the caller's cwd. (#166)
- `mpg setup --scope local --project-dir X` now runs every `claude mcp` call (add, remove, retry-add) in `X`, not the caller's cwd — previously only the advisory shadowing check resolved `project_dir` into a cwd, so mutating calls could silently register `mpg` somewhere other than the target project. (closes #164)
- README's example PostToolUse hook `matcher` used an unrecognized expression form that Claude Code evaluated as an unanchored regex matching every tool; corrected to `"Edit|Write"`.
- `setup_rules`/`setup_skills`'s non-symlink blocker message incorrectly attributed a flattened rule/skill file to "an older mpg version" that never existed — both delivery paths have been symlink-only since introduction. Corrected to describe symlink-flattening (git checkout on some platforms, backup/sync tooling) as the actual cause; the message is now shared between both call sites.

### Docs

- SECURITY.md now declares the supported 0.5.x line, an availability-dependent
  repository-owned private reporting URL with a bounded email fallback, the
  setup/uninstall mutation inventory, input and trust boundaries, and the
  guide supply-chain policy. A regression test derives the supported line from
  `pyproject.toml` to prevent policy drift. (closes #182)
- README and design documentation now cover dependency metadata, evidence precedence and lock-root limits, conservative status semantics, CLI/MCP controls, hook behavior, and additive output contracts. (closes #179)
- README documents the PostToolUse hook's actual shipped behavior (`additionalContext` contract, 5-match cap, `--no-hook`/`--with-hook` semantics, guide_id-only redaction rationale) and the `mpg setup` flags table.

## [0.5.10] — 2026-06-27

**Summary**: V5 benchmark runner now requires explicit `--allow-credit-use` opt-in for non-dry-run execution, and CI release-artifact invariants (build-verify-upload order, OIDC scope, no-rebuild-in-publish) are pinned by regression tests.

### Added

- Regression tests pin the verified-artifact release flow in `ci.yml`: build job verifies wheel assets before uploading, publish job reuses that verified artifact instead of rebuilding, `id-token: write` stays scoped to the publish job, and artifact upload is limited to release/workflow_dispatch events. Includes a negative-test fixture proving the pre-hardening workflow shape would fail the invariant. (closes #140)
- `bench/run-v5.sh` now requires `--allow-credit-use` for non-dry-run execution; `claude -p` benchmark sessions may consume credits depending on the account type. `--dry-run` output shows the session count and directs users to opt in explicitly. (closes #153)
- Tests for the credit-use guard: non-dry-run without `--allow-credit-use` exits 2, dry-run warns without requiring opt-in.

### Docs

- V5 benchmark reproduction docs restructured into cost/credit safety guidance, a low-cost manual path, and an automated path with dated budget wording.
- V1/V2 benchmark procedure (`docs/benchmark-procedure.md`) marked as historical with a cross-link to V5 and issue #124.

## [0.5.9] — 2026-06-20

**Summary**: JSON schema field-name sets in `docs/design.md` are now pinned to live serializer output via snapshot tests, and `ci.yml` + `publish.yml` are merged into a single workflow so the wheel published to PyPI is the exact artifact that passed CI verification.

### Added

- Snapshot tests pin `docs/design.md` JSON schema field-name sets (search, retrieve, list, not_found envelope) to live CLI/MCP serializer output. Adding or removing a field in either the serializer or design.md without updating the other now fails the test suite. Shared `extract_design_md_keys()` helper in `tests/conftest.py` replaces four hardcoded `expected_keys` locations. (closes #139)

### Changed

- `publish.yml` merged into `ci.yml`: the wheel published to PyPI is now the same artifact that passed `verify_wheel_assets.py`, eliminating the TOCTOU gap where a separately-built, unverified wheel was shipped. `id-token: write` is scoped to the publish job only (previously top-level in `publish.yml`). Artifact upload is conditional on release/dispatch events with 3-day retention. (closes #140)

## [0.5.8] — 2026-06-17

**Summary**: The PostToolUse hook's version-config walk now stops at `.git` repository boundaries, preventing silent adoption of external configs like `~/.python-version`.

### Fixed

- The PostToolUse hook's upward version-config walk (`find_configured_version`) now stops at the first directory containing `.git` (directory or file, covering normal repos, worktrees, and submodules). Previously the walk could escape the repository boundary and silently adopt configs like `~/.python-version` (a common pyenv artifact), causing every config-less project under `$HOME` to target a stale version instead of the default 3.11. The `.git`-bearing directory's own config is still checked before stopping, so monorepo roots with both `.git` and `pyproject.toml` work correctly. Nested repos (including submodules) are treated as separate projects — the inner `.git` stops the walk, and the outer repo's config is not inherited. Projects without `.git` (tarballs, vendored source) are unaffected: the walk continues to the depth limit as before. (closes #132)

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
