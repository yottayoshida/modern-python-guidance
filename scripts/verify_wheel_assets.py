#!/usr/bin/env python3
"""Verify that an installed (non-editable) wheel bundles its skills/ and rules/ assets.

The package's asset finders fall back to the source tree when the installed
package lacks the assets, so this script MUST be run from outside the
repository checkout against a wheel install (never ``pip install -e``):

    cd "$RUNNER_TEMP"
    env -u PYTHONPATH python "$GITHUB_WORKSPACE/scripts/verify_wheel_assets.py" "$GITHUB_WORKSPACE"

Exits non-zero with an actionable message when the wheel is missing assets.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

HINT = "check [tool.hatch.build.targets.wheel.sources] in pyproject.toml"


def fail(message: str) -> NoReturn:
    print(f"FAIL: {message}", file=sys.stderr)
    sys.exit(1)


def ensure_outside_checkout(label: str, path: Path, checkout: Path) -> None:
    if path.is_relative_to(checkout):
        fail(
            f"{label} resolved inside the checkout ({path}) — this verifies the source"
            " tree, not the wheel; run from outside the repo against a non-editable install"
        )


def relative_md_set(guides_dir: Path) -> set[str]:
    return {p.relative_to(guides_dir).as_posix() for p in guides_dir.rglob("*.md")}


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: verify_wheel_assets.py <checkout-root>")
    checkout = Path(sys.argv[1]).resolve()
    if not (checkout / "pyproject.toml").is_file():
        fail(f"{checkout} does not look like the repository checkout (no pyproject.toml)")
    ensure_outside_checkout("working directory", Path.cwd().resolve(), checkout)

    import modern_python_guidance
    from modern_python_guidance.setup_cmd import (
        SKILLS_LINK_NAME,
        _find_rule_source,
        _find_skills_dir,
    )

    module_path = Path(modern_python_guidance.__file__).resolve()
    ensure_outside_checkout("imported package", module_path, checkout)

    try:
        skills_dir = _find_skills_dir().resolve()
    except FileNotFoundError:
        fail(f"installed wheel is missing the bundled skills/ directory — {HINT}")
    try:
        rule_file = _find_rule_source().resolve()
    except FileNotFoundError:
        fail(f"installed wheel is missing the bundled rules/ file — {HINT}")

    ensure_outside_checkout("skills directory", skills_dir, checkout)
    ensure_outside_checkout("rule file", rule_file, checkout)

    pkg_root = module_path.parent
    for label, path in (("skills directory", skills_dir), ("rule file", rule_file)):
        if not path.is_relative_to(pkg_root):
            fail(
                f"{label} resolved outside the installed package ({path}, package at"
                f" {pkg_root}) — a stale external copy is masking the wheel contents; {HINT}"
            )

    if not (skills_dir / "SKILL.md").is_file():
        fail(f"SKILL.md is missing from the installed skills directory ({skills_dir}) — {HINT}")

    expected = relative_md_set(checkout / "skills" / SKILLS_LINK_NAME / "guides")
    if not expected:
        fail(
            "no guides found in the checkout — the expected-set glob is broken,"
            " refusing to pass on 0 == 0"
        )
    actual = relative_md_set(skills_dir / "guides")
    if expected != actual:
        missing = sorted(expected - actual) or "none"
        extra = sorted(actual - expected) or "none"
        fail(
            f"bundled guides do not match the checkout"
            f" (missing: {missing}, unexpected: {extra}) — {HINT}"
        )

    mpg_bin = Path(sys.executable).with_name("mpg")
    if not mpg_bin.is_file():
        fail(
            f"the 'mpg' console script is missing next to {sys.executable} — check"
            " [project.scripts] in pyproject.toml"
        )
    proc = subprocess.run(
        [str(mpg_bin), "list", "--format", "json"], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        detail = proc.stderr.strip() or proc.stdout.strip() or "no output"
        fail(
            f"'mpg list' against the installed wheel failed (exit {proc.returncode}: {detail})"
            f" — the wheel may have an empty guide index; {HINT}"
        )
    try:
        listed_ids = {entry["id"] for entry in json.loads(proc.stdout)}
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        fail(f"'mpg list --format json' produced unparseable output ({exc}) — {HINT}")
    # id == filename stem is enforced for the corpus by tests/test_guide_structure.py;
    # this re-derives expected ids without importing package internals
    expected_ids = {Path(rel).stem for rel in expected}
    if listed_ids != expected_ids:
        missing_ids = sorted(expected_ids - listed_ids) or "none"
        extra_ids = sorted(listed_ids - expected_ids) or "none"
        fail(
            f"'mpg list' does not index the expected guides"
            f" (missing: {missing_ids}, unexpected: {extra_ids}) — the bundled guide files"
            " are present, so the index failed to load some guides or a guide's"
            " frontmatter id diverges from its filename stem"
        )

    print(
        f"OK: wheel bundles SKILL.md, {len(actual)} guides, and {rule_file.name};"
        f" 'mpg list' indexes all {len(listed_ids)} guides"
    )


if __name__ == "__main__":
    main()
