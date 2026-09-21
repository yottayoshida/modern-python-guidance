from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY = REPO_ROOT / "SECURITY.md"
MARKER_RE = re.compile(r"<!-- supported-release-line: (\S+) -->")
NO_FIXES = "No release line receives security fixes"
SUPPORTED_ROW_RE = re.compile(r"\bsupported\b", re.IGNORECASE)


def assert_unmaintained_security_policy(text: str) -> None:
    """The project is no longer maintained, so SECURITY.md may neither name a
    supported release line nor offer a channel nobody answers.

    Until maintenance stopped this guard derived the supported line from
    `pyproject.toml` so a version bump could not leave the policy behind; with
    no further releases there is nothing to follow, and what has to hold is
    that nothing here promises a fix or a reply.
    """
    marker = MARKER_RE.search(text)
    assert marker is not None, "SECURITY.md lacks supported-release-line marker"
    assert marker.group(1) == "none", f"marker names a supported line: {marker.group(1)}"
    flat = text.replace("\n", " ")
    assert NO_FIXES in flat, "SECURITY.md does not say no line receives fixes"
    rows = [line for line in text.splitlines() if line.lstrip().startswith("|")]
    supported = [row for row in rows if SUPPORTED_ROW_RE.search(row)]
    assert not supported, f"table row calls a line supported: {supported}"
    assert "security/advisories/new" not in text, (
        "SECURITY.md points at the private reporting form"
    )
    assert "mailto:" not in text, "SECURITY.md offers a reporting mailbox"
    assert "read-only reference tool" not in text
    assert "does not" + " write to the filesystem" not in text


def test_security_policy_says_no_line_is_supported() -> None:
    assert_unmaintained_security_policy(POLICY.read_text(encoding="utf-8"))


def test_obsolete_policy_fixture_fails_the_guard() -> None:
    obsolete = """<!-- supported-release-line: 0.1.x -->
| 0.1.x | Supported |
This is a read-only reference tool and does not write to the filesystem.
"""
    with pytest.raises(AssertionError):
        assert_unmaintained_security_policy(obsolete)


SUPPORTED_TABLE = (
    "## Supported versions\n"
    "\n"
    "| Release line | Security fixes |\n"
    "|---|---|\n"
    "| 1.3.x | Supported |\n"
)


def _with(text: str, old: str, new: str) -> str:
    """Replace `old`, insisting it was there: a replacement that silently
    matched nothing would hand the guard the passing policy unchanged."""
    assert old in text, f"fixture edit found nothing to replace: {old!r}"
    return text.replace(old, new, 1)


@pytest.mark.parametrize(
    ("edit", "reason"),
    [
        (
            lambda t: _with(t, "supported-release-line: none", "supported-release-line: 1.3.x"),
            "marker names a supported line",
        ),
        (
            lambda t: _with(t, NO_FIXES, "Security fixes go to the latest minor release line"),
            "does not say no line receives fixes",
        ),
        (
            lambda t: _with(t, "## Supported versions\n", SUPPORTED_TABLE),
            "table row calls a line supported",
        ),
        (
            lambda t: (
                t
                + "\n<https://github.com/yottayoshida/modern-python-guidance/security/advisories/new>\n"
            ),
            "private reporting form",
        ),
        (lambda t: t + "\n[a mailbox](mailto:someone@example.invalid)\n", "reporting mailbox"),
    ],
    ids=["marker", "no-fixes-sentence", "supported-row", "reporting-form", "mailbox"],
)
def test_security_policy_guard_rejects_each_promise(edit, reason: str) -> None:
    """One promise added to the real policy at a time, each rejected for its
    own reason — so no single assertion can be carrying all of them."""
    real = POLICY.read_text(encoding="utf-8")
    with pytest.raises(AssertionError, match=reason):
        assert_unmaintained_security_policy(edit(real))


def _notes_for(project_root: Path) -> list[str]:
    """What setup/uninstall would disclose for this tree — same three write
    paths the orchestrators pass."""
    from modern_python_guidance.hook_config import settings_local_path, symlinked_parent_notes

    return symlinked_parent_notes(
        project_root,
        [
            project_root / ".claude" / "skills" / "modern-python-guidance",
            project_root / ".claude" / "rules" / "modern-python.md",
            settings_local_path(project_root),
        ],
    )


def test_policy_claims_followed_and_announced_not_confined() -> None:
    """The three claims are separable and each is load-bearing, so pin them
    separately: dropping any one leaves a policy that misdescribes the code.
    Nothing else ties this prose to behavior — the release-line guard above
    only checks the version table.
    """
    text = POLICY.read_text(encoding="utf-8")
    flat = text.replace("\n", " ")
    assert "followed, not rejected" in flat
    assert "the outermost symlinked directory on the way to it" in flat
    assert "not confinement" in text
    # The #192 boundary is gone: the disclosure no longer stops at `.claude`.
    assert "bounded" not in flat.split("## Inputs")[0]


def test_symlinked_claude_claim_matches_behavior(tmp_path: Path) -> None:
    """ "followed" and "announced", for a symlinked `.claude` (#170)."""
    elsewhere = tmp_path / "shared"
    elsewhere.mkdir()
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".claude").symlink_to(elsewhere, target_is_directory=True)

    notes = _notes_for(proj)
    assert len(notes) == 1, notes
    assert str(elsewhere.resolve()) in notes[0]


def test_policy_claim_about_inner_directories_matches_behavior(tmp_path: Path) -> None:
    """#192: the policy names `.claude/skills` and `.claude/rules` too."""
    text = POLICY.read_text(encoding="utf-8").replace("\n", " ")
    assert "`.claude/skills`" in text
    assert "`.claude/rules`" in text

    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    skills_target = tmp_path / "shared-skills"
    rules_target = tmp_path / "shared-rules"
    skills_target.mkdir()
    rules_target.mkdir()
    (proj / ".claude" / "skills").symlink_to(skills_target, target_is_directory=True)
    (proj / ".claude" / "rules").symlink_to(rules_target, target_is_directory=True)

    notes = _notes_for(proj)
    assert len(notes) == 2, notes
    joined = "\n".join(notes)
    assert str(skills_target.resolve()) in joined
    assert str(rules_target.resolve()) in joined


def test_policy_claim_notes_are_per_directory_not_per_destination(tmp_path: Path) -> None:
    """The policy says notes are per symlinked directory, "even if they happen
    to point at the same place". An earlier draft promised one note per distinct
    destination, which the code never did — pin the corrected claim so the two
    cannot drift apart again.
    """
    assert "not per destination" in POLICY.read_text(encoding="utf-8").replace("\n", " ")

    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    shared = tmp_path / "one-shared-dir"
    shared.mkdir()
    (proj / ".claude" / "skills").symlink_to(shared, target_is_directory=True)
    (proj / ".claude" / "rules").symlink_to(shared, target_is_directory=True)

    notes = _notes_for(proj)
    assert len(notes) == 2, notes
    assert all(str(shared.resolve()) in note for note in notes)
