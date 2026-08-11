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

The Python-version and run-form checks (#220) extend that shape and are
deliberately asymmetric — the floor must agree with `requires-python` in both
directions, while the advertised set need only be a subset of what CI runs. The
reason sits on `assert_declared_pythons_are_tested`.

License classifiers are absent here on purpose: #213 proposes dropping them as
deprecated under PEP 639, and a test defending something slated for removal
points the wrong way.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from packaging.version import Version

from modern_python_guidance.version_detect import _min_version_from_specifier

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
PY_TYPED = REPO_ROOT / "src" / "modern_python_guidance" / "py.typed"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

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


# --- Python versions and run form (#220) -----------------------------------

# Scoped to the `matrix:` block deliberately. The `build` job carries a bare
# `python-version: "3.13"` for packaging, and an unanchored pattern finds that
# one first — narrowing the "tested" set to a single entry while still
# reporting agreement.
_MATRIX_PYTHONS_RE = re.compile(r"matrix:\s*\n\s*python-version:\s*\[([^\]]*)\]")
_CLASSIFIER_PYTHON_RE = re.compile(r"^Programming Language :: Python :: (\d+\.\d+)$")
# Job keys sit at exactly two spaces under `jobs:`; everything inside a job is
# indented further, so this does not match `strategy:` or a job-level `name:`.
_JOB_KEY_RE = re.compile(r"^  ([A-Za-z_][\w-]*):\s*$", re.MULTILINE)


def ci_matrix_pythons(workflow_text: str) -> set[str]:
    """The Python versions CI's test matrix actually runs.

    Raises instead of returning an empty set when the block cannot be found.
    A pattern that stopped matching would turn every comparison below into
    `declared - set()`, which reports agreement exactly when the check has
    lost its footing — what `verify_wheel_assets.py` calls refusing to pass
    on 0 == 0.

    Then checks which job the match landed in. The pattern takes the first
    single-line `python-version` under any `matrix:`, and today only the test
    job has one — but a build or release matrix added above it would quietly
    become the evidence, turning versions nothing tests into proof that
    something does.
    """
    match = _MATRIX_PYTHONS_RE.search(workflow_text)
    if match is None:
        raise AssertionError(
            "no test-matrix python-version list found in ci.yml — this pattern expects a"
            " single-line array under `matrix:`; refusing to compare against an empty set"
        )
    jobs_above = _JOB_KEY_RE.findall(workflow_text[: match.start()])
    owner = jobs_above[-1] if jobs_above else "(no job key above the match)"
    assert owner == "test", (
        f"the matrix found belongs to job {owner!r}, not 'test' — a matrix in another job"
        " says nothing about what the test suite runs"
    )
    return {item.strip().strip("\"'") for item in match.group(1).split(",") if item.strip()}


def declared_pythons(classifiers: list[str]) -> set[str]:
    """The minor versions the classifiers advertise. The bare `:: 3` is not one."""
    matched = (_CLASSIFIER_PYTHON_RE.match(c) for c in classifiers)
    return {m.group(1) for m in matched if m}


def requires_python_floor(requires_python: str) -> str:
    """The lowest 3.x minor `requires-python` admits.

    Delegates to the function the package already applies to this very field:
    `version_detect._min_version_from_specifier`, called on `requires-python`
    at `version_detect.py:184`. It walks known minors asking the SpecifierSet,
    and also tries each minor's high patch — so `>3.11` counts as supporting
    3.11, because 3.11.1 installs and the classifier for 3.11 is therefore
    honest. A plain `contains("3.11")` denies that.

    Two earlier drafts of this helper were wrong in different ways. The first
    read the specifiers' written bounds and took their minimum, which answers
    3.11 for `>=3.11,>=3.12`. The second walked candidates itself — correct,
    but a second answer to a question the codebase already answers, free to
    drift from the one the CLI uses.
    """
    floor = _min_version_from_specifier(requires_python)
    assert floor is not None, f"no known Python minor satisfies {requires_python!r}"
    return floor


def assert_python_floor_agrees(requires_python: str, classifiers: list[str]) -> None:
    declared = declared_pythons(classifiers)
    assert declared, "no `Programming Language :: Python :: X.Y` classifier at all"
    lowest = min(declared, key=Version)
    expected = requires_python_floor(requires_python)
    assert lowest == expected, (
        f"the lowest declared Python is {lowest} but requires-python allows {expected}"
        " — one of the two tells installers something the other denies"
    )


def assert_declared_pythons_are_tested(classifiers: list[str], tested: set[str]) -> None:
    """One direction only: declared ⊆ tested.

    Not equality, and this repository's own history is the reason.
    `Programming Language :: Python :: 3.14` has been in pyproject since the
    initial scaffolding (d1c68bd), while CI gained 3.14 in #105 — a PR that
    changed ci.yml alone. Equality would make every commit before #105 a
    violation, and would forbid adding a Python to CI before committing to
    support it. What it still forbids is the reverse: advertising a version
    nothing runs.
    """
    assert tested, "the CI test matrix is empty"
    unbacked = sorted(declared_pythons(classifiers) - tested, key=Version)
    assert not unbacked, (
        f"classifiers advertise Python {unbacked}, which the CI test matrix does not run"
        f" (it runs {sorted(tested, key=Version)}) — a supported-version claim with no test"
        " behind it is the shape #206 removed for platforms"
    )


def assert_console_claim_has_a_script(classifiers: list[str], scripts: dict) -> None:
    """One direction only: claiming Console requires a script.

    The converse is not a defect. A package that ships a console script is
    under no obligation to advertise `Environment :: Console`, and asserting
    it would turn this into a completeness test for metadata rather than a
    check on the claims actually made.
    """
    if "Environment :: Console" not in classifiers:
        return
    assert scripts, "`Environment :: Console` is declared but [project.scripts] is empty"


def test_the_python_floor_agrees_with_requires_python() -> None:
    project = _project()
    assert_python_floor_agrees(project["requires-python"], project["classifiers"])


def test_every_declared_python_is_tested_in_ci() -> None:
    assert_declared_pythons_are_tested(
        _project()["classifiers"], ci_matrix_pythons(CI_WORKFLOW.read_text(encoding="utf-8"))
    )


def test_the_console_claim_is_backed_by_a_script() -> None:
    project = _project()
    assert_console_claim_has_a_script(project["classifiers"], project.get("scripts", {}))


def test_a_declared_python_below_requires_python_fails_the_guard() -> None:
    """3.9 rather than 3.10 on purpose: it is the case that separates version
    ordering from string ordering. `"3.10" < "3.11"` holds as text too, so a
    sort that forgot `key=Version` would fail this the same way and look
    correct — while `"3.11" < "3.9"` means the same bug keeps 3.11 as the
    minimum here and passes.
    """
    with pytest.raises(AssertionError):
        assert_python_floor_agrees(
            ">=3.11",
            [
                "Programming Language :: Python :: 3.9",
                "Programming Language :: Python :: 3.11",
            ],
        )


def test_raising_the_lowest_claim_above_requires_python_fails_the_guard() -> None:
    """The other direction of the same disagreement: dropping the floor
    classifier while `requires-python` still allows installing there."""
    with pytest.raises(AssertionError):
        assert_python_floor_agrees(">=3.11", ["Programming Language :: Python :: 3.12"])


def test_no_python_classifier_at_all_fails_the_guard() -> None:
    with pytest.raises(AssertionError):
        assert_python_floor_agrees(">=3.11", ["Environment :: Console"])


def test_an_untested_python_claim_fails_the_guard() -> None:
    with pytest.raises(AssertionError):
        assert_declared_pythons_are_tested(
            ["Programming Language :: Python :: 3.15"], {"3.11", "3.12"}
        )


def test_narrowing_the_matrix_below_a_claim_fails_the_guard() -> None:
    with pytest.raises(AssertionError):
        assert_declared_pythons_are_tested(["Programming Language :: Python :: 3.12"], {"3.11"})


def test_an_empty_matrix_fails_the_guard() -> None:
    """Distinct from the parser's own refusal: even handed a legitimately
    empty set, the comparison must not read it as agreement."""
    with pytest.raises(AssertionError):
        assert_declared_pythons_are_tested(["Programming Language :: Python :: 3.11"], set())


def test_withdrawing_a_claim_is_allowed() -> None:
    """The one-directional half, asserted rather than assumed. CI running a
    Python the classifiers do not advertise is how #105 landed, and a later
    edit tightening this to equality would break here rather than silently.
    """
    assert_declared_pythons_are_tested(
        ["Programming Language :: Python :: 3.11"], {"3.11", "3.12", "3.13"}
    )


def test_a_console_claim_without_scripts_fails_the_guard() -> None:
    with pytest.raises(AssertionError):
        assert_console_claim_has_a_script(["Environment :: Console"], {})


def test_no_console_claim_needs_no_script() -> None:
    """Also the one-directional half: scripts are required by the claim, not
    the other way round."""
    assert_console_claim_has_a_script(["Environment :: Web Environment"], {})


_CI_FIXTURE = """\
jobs:
  test:
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
  build:
    steps:
      - uses: actions/setup-python@0000000
        with:
          python-version: "3.13"
"""


def test_the_matrix_parser_reads_the_test_matrix() -> None:
    assert ci_matrix_pythons(_CI_FIXTURE) == {"3.11", "3.12"}


def test_the_matrix_parser_ignores_the_build_jobs_python() -> None:
    """`build` pins one version for packaging, which says nothing about what
    is tested. A pattern that matched it would shrink the tested set to a
    single entry and keep reporting agreement."""
    assert "3.13" not in ci_matrix_pythons(_CI_FIXTURE)


def test_the_matrix_parser_fails_when_the_matrix_is_absent() -> None:
    """The case that separates "nothing to compare" from "they agree"."""
    without_matrix = _CI_FIXTURE.replace('        python-version: ["3.11", "3.12"]\n', "")
    with pytest.raises(AssertionError, match="refusing to compare"):
        ci_matrix_pythons(without_matrix)


def test_the_matrix_parser_finds_the_real_workflow() -> None:
    """The fixtures prove the pattern handles a shape; this proves the shape
    is the one ci.yml actually has. Without it the whole group could pass
    against a synthetic file while the live check raised on every run."""
    assert ci_matrix_pythons(CI_WORKFLOW.read_text(encoding="utf-8"))


_CI_FIXTURE_FOREIGN_MATRIX = """\
jobs:
  release:
    strategy:
      matrix:
        python-version: ["3.9"]
  test:
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
"""


def test_the_matrix_parser_rejects_a_matrix_from_another_job() -> None:
    """The first `matrix:` in the file is not necessarily the test one, and
    the wrong one would supply evidence for versions nothing tests."""
    with pytest.raises(AssertionError, match="not 'test'"):
        ci_matrix_pythons(_CI_FIXTURE_FOREIGN_MATRIX)


def test_the_floor_takes_the_highest_lower_bound() -> None:
    """`>=3.11,>=3.12` admits nothing below 3.12. Reading the written bounds
    and taking their minimum answers 3.11 — which is what the first version of
    this helper did."""
    assert requires_python_floor(">=3.11,>=3.12") == "3.12"


def test_the_floor_skips_an_excluded_minor() -> None:
    """A surviving lower bound still nominally allows what `!=` removed."""
    assert requires_python_floor(">=3.11,!=3.11.*") == "3.12"


def test_an_exclusive_lower_bound_still_supports_that_minor() -> None:
    """`>3.11` excludes 3.11 exactly but admits 3.11.1, so a `:: 3.11`
    classifier is honest and the floor is 3.11 — not 3.12. The shared helper
    gets this by trying the minor's high patch; a bare `contains("3.11")`
    would answer 3.12 and quietly demand the classifier be dropped."""
    assert requires_python_floor(">3.11") == "3.11"


def test_the_floor_handles_a_wildcard_equality() -> None:
    """`==3.12.*` is a legal requires-python and is not a `Version`.
    `tests/test_version_detect.py` reads that form, so a guard raising
    InvalidVersion on it would be the only thing in the suite that could not."""
    assert requires_python_floor("==3.12.*") == "3.12"


def test_the_floor_answers_for_the_real_requires_python() -> None:
    """The cases above prove the walk handles expression shapes; this proves
    the live expression is one it can answer at all. The value is left to the
    floor test rather than pinned here, so the number lives in one place."""
    assert requires_python_floor(_project()["requires-python"]).startswith("3.")
