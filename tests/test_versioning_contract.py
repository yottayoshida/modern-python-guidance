"""What VERSIONING.md freezes, checked against what the code exposes.

Five surfaces are declared frozen. Three were already held: JSON output field
sets by `conftest.extract_design_md_keys` against design.md, the hook stdout
contract by `test_cli_unit.py`, and the frontmatter schema by `frontmatter.py`
refusing to parse violations. The two with no check at all were the CLI surface
and the MCP tool schemas, and those are what this file adds.

A frozen surface nothing reads back is the failure the document itself cites:
`Typing :: Typed` shipped false for 35 releases because no test looked (#204).
Declaring a freeze without checking it would repeat that inside the paragraph
warning against it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSIONING = REPO_ROOT / "docs" / "VERSIONING.md"

# The MCP input schemas as of the freeze, snapshotted whole rather than by
# parameter name. Names alone would let a type change from integer to string, an
# enum lose a value, or `limit.maximum` drop from 50 to 5 — client-visible breaks
# that a name comparison waves through.
#
# `maxItems` is stripped before comparison. It comes from `_guide_limit()` and
# tracks the catalog size, so pinning it would pin the catalog. The exclusion is
# stated in VERSIONING rather than left as a silent gap in the check.
FROZEN_SCHEMAS = REPO_ROOT / "tests" / "fixtures" / "frozen_mcp_schemas.json"

# The CLI surface as of the freeze: positionals and option names per command.
# `-h` / `--help` belong to argparse, not to this contract.
FROZEN_CLI: dict[str, tuple[set[str], set[str]]] = {
    "check": (
        {"file"},
        {
            "--dependency-version",
            "--exit-zero",
            "--format",
            "--project-dir",
            "--python-version",
            "--quiet",
        },
    ),
    "detect-version": (set(), {"--format", "--project-dir"}),
    "hook": ({"hook_name"}, set()),
    "list": (
        set(),
        {
            "--category",
            "--dependency-version",
            "--format",
            "--frequency",
            "--include-incompatible",
            "--layer",
            "--project-dir",
            "--python-version",
            "--with-content",
        },
    ),
    "mcp": (set(), set()),
    "retrieve": (
        {"ids"},
        {"--dependency-version", "--format", "--project-dir", "--python-version"},
    ),
    "search": (
        {"query"},
        {
            "--category",
            "--dependency-version",
            "--format",
            "--frequency",
            "--include-incompatible",
            "--layer",
            "--limit",
            "--project-dir",
            "--python-version",
        },
    ),
    "setup": (
        set(),
        {
            "--dry-run",
            "--mcp-only",
            "--no-hook",
            "--project-dir",
            "--scope",
            "--skills-only",
            "--with-hook",
        },
    ),
    "uninstall": (set(), {"--dry-run", "--mcp-only", "--project-dir", "--skills-only"}),
}


def _frozen_names(heading: str, text: str | None = None) -> set[str]:
    """The names in the first fenced block after a heading.

    Searching from the heading rather than across the whole file: several of
    these names appear in prose elsewhere, and a file-wide search would find
    them there and report an agreement the frozen list never declared.

    There is deliberately no section boundary. An earlier version computed one,
    and falsification showed it changed nothing: `re.search` stops at the first
    block either way. If a surface's own list were deleted, the search finds the
    next surface's and the comparison fails — the right outcome, pinned by
    `test_a_surface_without_a_list_borrows_the_next_one` below. A branch no
    input can exercise is a check nothing runs.
    """
    if text is None:
        text = VERSIONING.read_text(encoding="utf-8")
    start = text.index(heading)
    match = re.search(r"```\n(.+?)\n```", text[start:], re.DOTALL)
    assert match is not None, f"no fenced name list under {heading!r}"
    return set(match.group(1).split())


def test_the_frozen_cli_commands_match_the_parser() -> None:
    from modern_python_guidance.cli import COMMAND_GROUPS

    registered = {name for _title, entries in COMMAND_GROUPS for name, _desc in entries}
    declared = _frozen_names("### 1. CLI surface")
    assert declared == registered, (
        f"VERSIONING freezes {sorted(declared)} but the parser registers"
        f" {sorted(registered)} — one of the two changed without the other"
    )


def test_the_frozen_mcp_tools_match_the_server() -> None:
    from modern_python_guidance.mcp_server import _get_tools

    served = {tool["name"] for tool in _get_tools()}
    declared = _frozen_names("### 2. MCP tool schemas")
    assert declared == served, (
        f"VERSIONING freezes {sorted(declared)} but the server serves {sorted(served)}"
    )


def _strip_dynamic(node: object) -> object:
    """The schema minus the parts that move with the catalog.

    Only `maxItems`, and only because `_guide_limit()` derives it from how many
    guides exist. Everything else — types, enums, bounds, defaults — is part of
    what a client can break against and stays in the comparison.
    """
    if isinstance(node, dict):
        return {k: _strip_dynamic(v) for k, v in node.items() if k != "maxItems"}
    if isinstance(node, list):
        return [_strip_dynamic(v) for v in node]
    return node


def test_the_frozen_mcp_input_schemas_match_the_server() -> None:
    """Whole schemas, not just parameter names.

    A name-only comparison passes a `layer` that changed from integer to
    string, an enum that lost a value, and a `limit.maximum` cut from 50 to 5.
    Each of those is visible to a client and breaks it.
    """
    from modern_python_guidance.mcp_server import _get_tools

    frozen = json.loads(FROZEN_SCHEMAS.read_text(encoding="utf-8"))
    actual = {tool["name"]: _strip_dynamic(tool["inputSchema"]) for tool in _get_tools()}
    assert actual == frozen


def test_the_frozen_cli_options_match_the_parser() -> None:
    """Command names alone would let `--format` or `--with-content` disappear
    in a minor release. The freeze covers the option names too, so the parser
    is read back per command."""
    from modern_python_guidance.cli import build_parser

    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(getattr(action, "choices", None), dict)
    )
    actual = {
        name: (
            {a.dest for a in sub._actions if not a.option_strings},
            {o for a in sub._actions for o in a.option_strings if o not in ("-h", "--help")},
        )
        for name, sub in subparsers.choices.items()
    }
    assert actual == FROZEN_CLI


def test_the_snapshot_still_excludes_the_catalog_derived_field() -> None:
    """The premise of the exclusion, checked separately from the exclusion.

    A broken `_strip_dynamic` is caught by the comparison above, not here —
    measured, after this docstring first claimed otherwise. What this pins is
    the premise: `retrieve_guides` still carries a catalog-derived `maxItems`,
    and the snapshot still does not. If the schema stopped carrying it, the
    exclusion would remain written down while protecting nothing, and the
    comparison would pass either way because both sides would simply lack it.
    """
    from modern_python_guidance.mcp_server import _get_tools

    served = {tool["name"]: tool["inputSchema"] for tool in _get_tools()}
    assert "maxItems" in json.dumps(served["retrieve_guides"]), (
        "retrieve_guides no longer carries maxItems; this control no longer proves anything"
    )
    assert "maxItems" not in FROZEN_SCHEMAS.read_text(encoding="utf-8")


def test_each_surface_reads_its_own_list_and_not_the_next() -> None:
    """The live document: the two fenced lists do not bleed into each other."""
    assert "search_guides" not in _frozen_names("### 1. CLI surface")
    assert "search" not in _frozen_names("### 2. MCP tool schemas")


def test_a_surface_without_a_list_borrows_the_next_one() -> None:
    """Pinning the failure mode rather than preventing it.

    With no section boundary, a surface whose fenced list was deleted picks up
    the following surface's. That is deliberate: the borrowed names will not
    match what that surface's holder registers, so the comparison fails and
    says so. The alternative — returning an empty set — would compare nothing
    against nothing and report agreement.
    """
    synthetic = (
        "### 1. CLI surface\n\nthe list was deleted\n\n"
        "### 2. MCP tool schemas\n\n```\nsearch_guides\n```\n"
    )
    assert _frozen_names("### 1. CLI surface", synthetic) == {"search_guides"}


def test_every_frozen_surface_names_what_holds_it() -> None:
    """The document's own rule, applied to itself: each surface says what keeps
    it honest. A surface listed without a holder is the state #204 was in."""
    text = VERSIONING.read_text(encoding="utf-8")
    frozen = text.split("## Frozen surfaces", 1)[1].split("\n## Not frozen", 1)[0]
    sections = [s for s in re.split(r"\n### ", frozen) if s.strip()]
    assert len(sections) == 5, f"expected 5 frozen surfaces, found {len(sections)}"
    for section in sections:
        title = section.splitlines()[0]
        assert "Held by" in section or "enforced at parse time" in section, (
            f"frozen surface {title!r} names nothing that holds it"
        )


def test_every_named_holder_exists() -> None:
    """The check above reads words; this one resolves them.

    "Held by `tests/nonexistent.py`" satisfies a search for the phrase and
    holds nothing. Three of the five surfaces delegate to tests written
    elsewhere, so the names have to resolve or the delegation is fiction.
    """
    from modern_python_guidance import frontmatter

    text = VERSIONING.read_text(encoding="utf-8")

    named_files = set(re.findall(r"`(tests/[\w/]+\.py)", text))
    assert named_files, "VERSIONING names no test files at all"
    for relative in sorted(named_files):
        assert (REPO_ROOT / relative).is_file(), f"VERSIONING names {relative}, which is absent"

    for symbol in ("REQUIRED_FIELDS", "VALID_LAYERS", "VALID_FREQUENCIES"):
        assert symbol in text, f"VERSIONING stopped naming {symbol} as the frontmatter holder"
        assert hasattr(frontmatter, symbol), f"frontmatter no longer defines {symbol}"

    # `tests` is not a package, so the conftest helper cannot be imported by
    # name here; read the file it lives in instead.
    assert "extract_design_md_keys" in text
    conftest = (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "def extract_design_md_keys" in conftest, (
        "VERSIONING names extract_design_md_keys as the JSON-shape holder, but"
        " conftest no longer defines it"
    )
