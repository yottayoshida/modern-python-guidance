"""The metadata this package ships to PyPI, read back against the tree.

A classifier is a promise made to every consumer's tooling, and nothing here was
reading them back. `Typing :: Typed` reached PyPI for 35 releases while the PEP
561 marker was absent from the source tree and from every published wheel, so
type checkers ignored the annotations the classifier advertised (#204).
`Development Status :: 3 - Alpha` survived just as long for the same reason
(#207).

The version-derived checks follow the shape `test_security_policy.py` already
uses for SECURITY.md: a helper that takes its inputs as arguments, the real tree
passed through it, and synthetic inputs proving the helper rejects the drift it
exists to catch.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
PY_TYPED = REPO_ROOT / "src" / "modern_python_guidance" / "py.typed"

# The platforms something has actually run on: CI covers Linux, development
# happens on macOS. Windows is absent on purpose — see README's Supported
# platforms section, which this set is meant to stay in step with.
PLATFORMS_WITH_EVIDENCE = {
    "Operating System :: MacOS",
    "Operating System :: POSIX :: Linux",
}


def _project() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]


def expected_development_status(version: str) -> str:
    """The status a given version is allowed to advertise.

    A final 1.0 or later must say Production/Stable: a release that calls itself
    1.0 while its own PyPI page says Alpha contradicts itself. This lives in a
    test rather than in a release checklist so the version bump and the
    classifier cannot land in separate commits — the same reason SECURITY.md's
    supported release line is pinned to the version rather than to a reminder.

    Prereleases of 1.0 are exempt. `1.0.0rc1` is where a project finds out
    whether it is stable, so requiring the stable classifier there would force
    the claim before the evidence — and `Version.is_prerelease` covers the dev
    and alpha/beta forms too.
    """
    parsed = Version(version)
    if parsed.major >= 1 and not parsed.is_prerelease:
        return "5 - Production/Stable"
    return "4 - Beta"


def assert_development_status(version: str, classifiers: list[str]) -> None:
    expected = f"Development Status :: {expected_development_status(version)}"
    found = [c for c in classifiers if c.startswith("Development Status ::")]
    assert found == [expected], f"version {version} requires {expected!r}, found {found!r}"


def assert_typing_promise_is_kept(*, classifier: bool, marker: bool) -> None:
    assert classifier == marker, (
        f"'Typing :: Typed' classifier present: {classifier}, py.typed present: {marker}."
        " A classifier without the marker makes every installation untyped under PEP 561;"
        " a marker without the classifier hides that the package ships types at all."
    )


def test_development_status_matches_the_current_version() -> None:
    project = _project()
    assert_development_status(project["version"], project["classifiers"])


def test_a_1_0_release_still_calling_itself_beta_fails_the_guard() -> None:
    with pytest.raises(AssertionError):
        assert_development_status("1.0.0", ["Development Status :: 4 - Beta"])


def test_a_pre_1_0_release_claiming_stable_fails_the_guard() -> None:
    """The other direction. Without this, an assertion that always passed on
    0.x would look just as green as one that works."""
    with pytest.raises(AssertionError):
        assert_development_status("0.6.0", ["Development Status :: 5 - Production/Stable"])


def test_a_missing_development_status_fails_the_guard() -> None:
    with pytest.raises(AssertionError):
        assert_development_status("0.6.0", ["Environment :: Console"])


def test_a_1_0_prerelease_may_still_say_beta() -> None:
    """Otherwise cutting `1.0.0rc1` would force the stable claim before the
    release candidate had a chance to earn it."""
    assert_development_status("1.0.0rc1", ["Development Status :: 4 - Beta"])
    assert_development_status("1.0.0a1", ["Development Status :: 4 - Beta"])
    assert_development_status("1.0.0.dev1", ["Development Status :: 4 - Beta"])


def test_a_1_0_prerelease_may_not_claim_stable_either() -> None:
    with pytest.raises(AssertionError):
        assert_development_status("1.0.0rc1", ["Development Status :: 5 - Production/Stable"])


def test_typing_classifier_and_pep_561_marker_agree() -> None:
    assert_typing_promise_is_kept(
        classifier="Typing :: Typed" in _project()["classifiers"],
        marker=PY_TYPED.is_file(),
    )


def test_the_typing_guard_rejects_either_half_alone() -> None:
    with pytest.raises(AssertionError):
        assert_typing_promise_is_kept(classifier=True, marker=False)
    with pytest.raises(AssertionError):
        assert_typing_promise_is_kept(classifier=False, marker=True)


def test_the_marker_sits_inside_the_importable_package() -> None:
    """Inside the package, not beside it.

    `src/py.typed` would satisfy "the file exists" while staying invisible to
    every type checker, because PEP 561 looks for the marker in the installed
    package directory — the one holding __init__.py.

    Comparing PY_TYPED.parent against the path PY_TYPED was built from would be
    a tautology: two path objects, no filesystem. The first draft did exactly
    that and survived the marker being renamed away.
    """
    assert PY_TYPED.is_file(), f"{PY_TYPED} is missing"
    assert (PY_TYPED.parent / "__init__.py").is_file(), (
        f"{PY_TYPED.parent} holds no __init__.py, so it is not the importable package"
        " — a marker placed beside the package is one no type checker consults"
    )


def test_the_declared_platforms_are_exactly_the_ones_backed_by_evidence() -> None:
    """#206: the package shipped with no statement about where it runs, while
    `mpg setup` depends on symlink creation being permitted.

    The exact set matters more than the count. Windows is deliberately absent —
    nothing has run there — and "at least one OS classifier" would keep passing
    if someone added it, or `OS Independent`, leaving the metadata claiming a
    platform README calls untested. Widening this set is a decision that should
    require editing README in the same commit, which is what a hard-coded set
    forces.
    """
    declared = {c for c in _project()["classifiers"] if c.startswith("Operating System ::")}
    assert declared == PLATFORMS_WITH_EVIDENCE, (
        f"declared {sorted(declared)}, expected {sorted(PLATFORMS_WITH_EVIDENCE)} — if a"
        " platform gained or lost coverage, update README's Supported platforms section"
        " in the same change"
    )
