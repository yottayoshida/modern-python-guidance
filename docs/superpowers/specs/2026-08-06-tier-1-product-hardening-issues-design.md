# Tier 1 Product-Hardening Issue Design

Date: 2026-08-06

## Objective

Create a minimal set of GitHub issues for product problems that currently block trustworthy
shipping, adoption, or delivery of modern-python-guidance's core value. Growth work, minor
quality improvements, and already-tracked implementation defects are outside this Tier 1 set.

## Triage rules

- Each issue must describe one independently solvable root problem.
- Each issue must cite observable repository evidence rather than inferred user behavior.
- Existing issues must be linked when related, but not duplicated.
- Every issue must use the `tier:1-ship` label plus the narrowest applicable `area:*` labels.
- Acceptance criteria must describe an observable product outcome without prescribing an
  unnecessary implementation.

## Issue 1: Make guide applicability dependency-aware for framework and tool versions

Labels: `enhancement`, `tier:1-ship`, `area:content`, `area:integration`

### Problem

Guide applicability is filtered only by the target Python version. Eighteen Layer 2 guides and
several toolchain guides also depend on package or tool versions, but that compatibility is
expressed only in prose. The search, retrieve, list, Rules, Skill, and hook delivery paths cannot
exclude guidance that is incompatible with the project's installed dependency versions.

Examples include Pydantic V2 migration guidance, FastAPI features introduced in specific
releases, Django API changes, SQLAlchemy 2.0 style, and httpx version requirements. A project
using Pydantic V1 or an older Django/FastAPI release can therefore receive a recommendation
that its environment cannot run.

### Product impact

Version awareness is a headline product promise. Applying it only to Python creates a false
sense of compatibility precisely where framework migration advice carries the most breakage
risk. Incorrect guidance damages trust more than missing guidance.

### Scope

Define and enforce an applicability contract for dependency-sensitive guides. The solution may
use detected project dependencies, explicit caller-provided dependency versions, compatibility
metadata returned to the agent, or a safe combination. When compatibility cannot be determined,
the product must not present an uncertain recommendation as unconditionally applicable.

### Acceptance criteria

- Dependency-sensitive guides declare machine-readable package or tool compatibility.
- At least Pydantic, FastAPI, Django, SQLAlchemy, httpx, and pytest guides are covered.
- CLI and MCP outputs expose whether dependency compatibility is confirmed, incompatible, or
  unknown.
- Automatic delivery paths do not instruct an agent to apply a known-incompatible guide.
- Tests cover supported, unsupported, and unknown dependency-version cases.
- User documentation explains the difference between Python compatibility and dependency
  compatibility.

## Issue 2: Honor automatic target-Python detection across CLI and MCP guidance paths

Labels: `bug`, `tier:1-ship`, `area:cli`, `area:integration`, `area:docs`

### Problem

The README presents automatic target-Python detection as a product-wide capability and says the
CLI auto-detects the project's version. In the implementation, `search`, `retrieve`, `list`, and
their MCP equivalents pass `python_version=None` unless the caller explicitly supplies a value.
Only `detect-version` and the Claude PostToolUse hook perform automatic detection.

As a result, the primary discovery and retrieval paths can return guides that require a newer
Python version than the project supports, even when a valid `requires-python` or
`.python-version` file is present.

### Product impact

This contradicts the core "version-aware" promise and can cause agents or developers to select
syntax and APIs that fail in the target environment. Requiring an agent to call a separate MCP
tool and correctly forward its result also makes correctness depend on probabilistic tool-use
behavior.

### Scope

Establish one explicit version-resolution contract shared by CLI, MCP, and automatic delivery
paths. Preserve an explicit version override. If any path intentionally remains opt-in, the
documentation and output must state that limitation rather than claiming automatic filtering.

### Acceptance criteria

- With a supported project version file present, CLI search, retrieve, and list resolve the same
  target Python version without requiring `--python-version`.
- MCP search, retrieve, and list do not depend on the model making a separate detection call to
  avoid known-incompatible guides.
- Explicit version arguments override detected values consistently.
- Output exposes the resolved version and its source so users can audit filtering decisions.
- Tests cover `requires-python`, Poetry constraints, `.python-version`, explicit overrides, and
  the no-configuration fallback.
- README and MCP tool descriptions match the implemented behavior.

## Issue 3: Do not claim full-catalog hook coverage while 15 guides are non-detectable

Labels: `bug`, `tier:1-ship`, `area:integration`, `area:docs`, `area:testing`

### Problem

The README states that the PostToolUse hook checks edited Python files against the full 41-guide
catalog. The guide index currently contains 41 guides, but only 26 have `detect-patterns` or
`detect-names`; 15 explicitly opt out of detection. The hook calls `check_file()`, so those 15
guides cannot produce a finding.

This is distinct from #152, which tracks whether the product activates and reaches the full
catalog during real development sessions. This issue concerns the accuracy and completeness of
the hook's declared checking contract after activation.

### Product impact

Users are told that setup provides a comprehensive safety net, while more than one third of the
catalog is invisible to that safety net. Silent coverage gaps make a clean hook result easy to
misinterpret as full-catalog compliance.

### Scope

Define the hook's supported coverage explicitly. Either add reliable detection for guides where
that is technically appropriate, or report and document which guides are advisory-only. Do not
add low-confidence matchers merely to increase a coverage count.

### Acceptance criteria

- The product has a machine-verifiable distinction between detectable and advisory-only guides.
- Hook and `mpg check` output identify the scope of the completed check, including coverage gaps
  relevant to the target project.
- README no longer describes advisory-only guides as actively checked.
- Each guide's detection status is visible through CLI or MCP metadata.
- Structural tests fail when documentation, metadata, and actual detection coverage diverge.
- The relationship to #152 is documented without duplicating its activation success metric.

## Issue 4: Update SECURITY.md to match the current setup and hook attack surface

Labels: `documentation`, `tier:1-ship`, `security`, `area:docs`, `area:integration`

### Problem

`SECURITY.md` supports only `0.1.x`, while the package version is `0.5.10`. It also describes the
project as a read-only reference tool that does not write to the filesystem or process untrusted
input beyond CLI arguments. The current product can write and remove project configuration,
create symlinks, update `.claude/settings.local.json`, invoke the `claude` CLI, and process edited
file paths and source files through the PostToolUse hook.

The implementation contains meaningful safeguards for these operations, but the published
security model does not describe them or the remaining trust boundaries.

### Product impact

Security documentation is part of the trust contract for a tool installed into coding-agent
workflows. Incorrectly denying the product's mutation and input surfaces prevents users and
security reviewers from making an informed installation decision and can misroute vulnerability
reports.

### Scope

Replace the obsolete description with a threat model for the shipped product. Cover setup,
uninstall, hook execution, MCP path confinement, guide supply chain, local configuration writes,
and external process invocation. Keep claims bounded to verified behavior.

### Acceptance criteria

- The supported-version policy covers the currently released line and states how old releases
  are handled.
- `SECURITY.md` accurately inventories filesystem mutations, symlink behavior, subprocess calls,
  parsed project files, and hook inputs.
- Trust boundaries and current mitigations are documented for setup, uninstall, MCP, and hooks.
- The guide-content supply-chain risk includes a review or verification policy, not only a list
  of two security-themed guides.
- Vulnerability reporting instructions use a maintainable contact channel and define expected
  response behavior without promising unsupported guarantees.
- A documentation test or release checklist prevents the supported-version table from silently
  falling behind the package version again.

## Issue 5: Calibrate effectiveness claims to the benchmark's actual scope and delivery mechanism

Labels: `documentation`, `tier:1-ship`, `area:docs`, `area:testing`, `area:strategy`

### Problem

The README headline says "AI writes modern Python 98% of the time with mpg, vs 79% without."
Those figures are the Opus 4.8 terse-prompt result from Benchmark V5: N=3, one FastAPI web-app
variant, and a treatment that loads the complete `SKILL.md` as a Rules file. The metric also
excludes patterns that the model did not emit. This is not the same delivery shape as selective
MCP retrieval, the thin shipped Rules file, or the PostToolUse hook.

The benchmark document discloses these limitations, but the product headline generalizes across
models, workloads, patterns, and delivery methods.

### Product impact

The benchmark is useful directional evidence, but an over-broad headline creates credibility and
adoption risk. Users evaluating an agent-integrated quality tool need to know which product path
was measured and what the percentage means.

### Scope

Keep measurable evidence prominent while making every claim traceable to a reproducible benchmark
cell. Separate content-efficacy evidence from real-product delivery effectiveness. Add a benchmark
or claim matrix for the delivery paths the product actually ships.

### Acceptance criteria

- README claims name the tested model, prompt style, sample size, workload, metric denominator,
  and treatment delivery method close to the headline.
- No product-level claim generalizes a single benchmark cell to unspecified AI models or project
  types.
- Benchmark documentation distinguishes full-content Rules injection, the shipped thin Rules
  file, MCP retrieval, Skill activation, and hook/check delivery.
- At least one benchmark exercises the default `mpg setup` product path end to end, or the README
  explicitly states that end-to-end effectiveness is not yet measured.
- Raw run inputs and scorer version are traceable from each promoted result.
- A review check prevents README benchmark numbers from diverging from their source table.

## Existing-issue handling

- Link Issue 3 to #152; do not replace or duplicate #152.
- Do not reclassify #166, #167, or #170 as Tier 1 in this batch. They describe narrower setup or
  symlink edge cases and do not meet the adopted Tier 1 threshold without additional evidence.
- Do not reopen #54. Its benchmark-delivery disclosure improved the detailed documentation, while
  Issue 5 addresses the remaining product-headline generalization.

## Verification

After issue creation:

1. Confirm exactly five new open issues exist with the approved titles.
2. Confirm every issue body is English and contains Problem, Product impact, Scope, and Acceptance
   criteria sections.
3. Confirm every issue has `tier:1-ship` and only existing repository labels.
4. Confirm Issue 3 links to #152 and Issue 5 does not create an unintended reference to an
   unrelated issue.
5. Return the five issue URLs and a one-line rationale for the priority order.
