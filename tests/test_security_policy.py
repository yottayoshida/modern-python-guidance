from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY = REPO_ROOT / "SECURITY.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"
MARKER_RE = re.compile(r"<!-- supported-release-line: (\d+\.\d+\.x) -->")


def expected_release_line() -> str:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    version = Version(data["project"]["version"])
    return f"{version.major}.{version.minor}.x"


def assert_current_security_policy(text: str) -> None:
    marker = MARKER_RE.search(text)
    assert marker is not None, "SECURITY.md lacks supported-release-line marker"
    assert marker.group(1) == expected_release_line()
    assert f"| {expected_release_line()} | Supported |" in text
    assert "security/advisories/new" in text
    assert "read-only reference tool" not in text
    assert "does not" + " write to the filesystem" not in text


def test_security_policy_matches_current_release_line() -> None:
    assert_current_security_policy(POLICY.read_text(encoding="utf-8"))


def test_obsolete_policy_fixture_fails_the_guard() -> None:
    obsolete = """<!-- supported-release-line: 0.1.x -->
| 0.1.x | Supported |
This is a read-only reference tool and does not write to the filesystem.
"""
    with pytest.raises(AssertionError):
        assert_current_security_policy(obsolete)


def test_symlinked_claude_claim_matches_behavior(tmp_path: Path) -> None:
    """#170: the policy says a symlinked `.claude` is followed and announced.
    Both halves are load-bearing, and nothing else ties this prose to the code
    — the release-line guard above only checks the version table. Pin the
    document against the behavior it describes.
    """
    from modern_python_guidance.hook_config import symlinked_claude_note

    text = POLICY.read_text(encoding="utf-8")
    assert "followed,\nnot rejected" in text or "followed, not rejected" in text
    assert "not confinement" in text

    elsewhere = tmp_path / "shared"
    elsewhere.mkdir()
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".claude").symlink_to(elsewhere, target_is_directory=True)

    # "followed": no exception, no refusal.
    note = symlinked_claude_note(proj)
    # "announced": and it names where the write actually goes.
    assert note is not None
    assert str(elsewhere.resolve()) in note
