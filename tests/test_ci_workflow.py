"""Regression tests for release artifact verification in CI."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CI_WORKFLOW = WORKFLOWS / "ci.yml"
RELEASE_CHECKER_WORKFLOW = WORKFLOWS / "check-python-release.yml"
AUDIT_WORKFLOW = WORKFLOWS / "audit-dependencies.yml"


OLD_UNVERIFIED_PUBLISH_WORKFLOW = """
name: Publish to PyPI

permissions:
  contents: read
  id-token: write

jobs:
  build:
    steps:
      - name: Build sdist and wheel
        run: python -m build

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  publish:
    needs: build
    steps:
      - name: Download artifacts
        uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
"""


def workflow_text() -> str:
    return CI_WORKFLOW.read_text(encoding="utf-8")


def publish_job(text: str) -> str:
    marker = "\n  publish:\n"
    assert marker in text
    return text.split(marker, maxsplit=1)[1]


def assert_build_verifies_wheel_before_uploading_dist(text: str) -> None:
    build = text.index("  build:")
    assert "scripts/verify_wheel_assets.py" in text
    verify = text.index("scripts/verify_wheel_assets.py", build)
    upload = text.index("actions/upload-artifact@", verify)

    assert build < verify < upload
    assert "working-directory: ${{ runner.temp }}" in text
    assert 'env -u PYTHONPATH python "$GITHUB_WORKSPACE/scripts/verify_wheel_assets.py"' in text
    assert "name: dist" in text
    assert "path: dist/" in text


def build_job_upload_step(text: str) -> str:
    upload_step = text.index("      - name: Upload artifacts")
    publish = text.index("\n  publish:\n")
    return text[upload_step:publish]


def assert_publish_reuses_verified_dist(text: str) -> None:
    publish = publish_job(text)

    assert "needs: [test, build]" in publish
    assert "actions/download-artifact@" in publish
    assert "name: dist" in publish
    assert "path: dist/" in publish
    assert "python -m build" not in publish
    assert 'pip install "build' not in publish


def test_build_verifies_wheel_assets_before_uploading_dist() -> None:
    assert_build_verifies_wheel_before_uploading_dist(workflow_text())


def test_publish_reuses_verified_dist_artifact_instead_of_rebuilding() -> None:
    assert_publish_reuses_verified_dist(workflow_text())


def test_dist_artifact_upload_is_limited_to_publish_capable_events() -> None:
    upload_step = build_job_upload_step(workflow_text())

    assert (
        "if: github.event_name == 'release' || github.event_name == 'workflow_dispatch'"
        in upload_step
    )


def test_old_publish_workflow_would_not_satisfy_verified_artifact_invariant() -> None:
    with pytest.raises(AssertionError, match="verify_wheel_assets"):
        assert_build_verifies_wheel_before_uploading_dist(OLD_UNVERIFIED_PUBLISH_WORKFLOW)


def test_pypi_oidc_permission_is_scoped_to_publish_job() -> None:
    text = workflow_text()
    top_level_permissions = text.split("\njobs:\n", maxsplit=1)[0]

    assert "id-token: write" not in top_level_permissions
    assert "permissions:\n      id-token: write" in publish_job(text)


# --- scheduled workflows: permissions and triggers ---


def header(text: str) -> str:
    """Everything above `jobs:`, with comments stripped.

    Comments have to go: these workflows explain *why* a scope is declared
    right above the declaration, so a plain substring search is satisfied by
    the explanation alone. Deleting the `contents: read` line while leaving its
    comment kept this file green until that was measured.
    """
    assert "\njobs:\n" in text
    above_jobs = text.split("\njobs:\n", maxsplit=1)[0]
    return "\n".join(line for line in above_jobs.splitlines() if not line.lstrip().startswith("#"))


def assert_checkout_permission_declared(text: str) -> None:
    """Declaring `permissions` at all drops every scope not listed, so a job
    that checks out the repository has to ask for `contents: read` (#163)."""
    perms = header(text)
    assert "actions/checkout@" in text, "no checkout step; this check does not apply"
    assert "contents: read" in perms, "checkout without contents: read"


def assert_not_triggered_by_pull_requests(text: str) -> None:
    """Assert the absence, not just the presence of `schedule`: a check that
    only looked for `schedule` would pass unchanged if `pull_request` were
    added alongside it."""
    on_block = header(text).split("\non:\n", maxsplit=1)[1]
    on_block = on_block.split("\npermissions:", maxsplit=1)[0]
    assert "schedule:" in on_block
    assert "pull_request" not in on_block
    assert "push:" not in on_block


WORKFLOW_WITHOUT_CHECKOUT_PERMISSION = """
name: Example

on:
  schedule:
    - cron: '0 9 * * 1'

permissions:
  issues: write

jobs:
  check:
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4.3.1
"""

WORKFLOW_ALSO_RUNNING_ON_PULL_REQUESTS = """
name: Example

on:
  schedule:
    - cron: '0 9 * * 1'

  pull_request:

permissions:
  contents: read

jobs:
  check:
    steps:
      - run: echo hi
"""

WORKFLOW_WITH_THE_PERMISSION_ONLY_IN_A_COMMENT = """
name: Example

on:
  schedule:
    - cron: '0 9 * * 1'

# `contents: read` is required for actions/checkout.
permissions:
  issues: write

jobs:
  check:
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4.3.1
"""


def test_release_checker_can_check_out_the_repository() -> None:
    assert_checkout_permission_declared(RELEASE_CHECKER_WORKFLOW.read_text(encoding="utf-8"))


def test_release_checker_keeps_issue_write_and_adds_nothing_else() -> None:
    perms = header(RELEASE_CHECKER_WORKFLOW.read_text(encoding="utf-8"))
    assert "issues: write" in perms
    assert perms.count(": write") == 1, "an unrelated write scope was added"


def test_audit_workflow_can_check_out_the_repository() -> None:
    assert_checkout_permission_declared(AUDIT_WORKFLOW.read_text(encoding="utf-8"))


def test_audit_workflow_does_not_run_on_pull_requests() -> None:
    """The audit reports advisories against third-party packages, which have
    nothing to do with the change under review."""
    assert_not_triggered_by_pull_requests(AUDIT_WORKFLOW.read_text(encoding="utf-8"))


def test_audit_workflow_delegates_the_verdict_to_the_tested_script() -> None:
    """The decision of whether a run established anything lives in a script
    with fixtures, not in inline shell that nothing can exercise."""
    text = AUDIT_WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/check_dependency_audit.py" in text
    assert "--audit-exit=" in text
    # `uv audit` exits non-zero on findings; without capturing that the step
    # would abort before anything could be reported.
    assert "set +e" in text


def test_audit_workflow_keys_the_issue_on_the_advisory_set() -> None:
    """A fixed title would let a closed issue about old advisories suppress a
    new one. The search is a phrase match, so an exact title comparison has to
    follow it."""
    text = AUDIT_WORKFLOW.read_text(encoding="utf-8")
    assert "--issue-title" in text
    assert "--state open" in text
    assert 'select(.title == \\"${TITLE}\\")' in text


def test_audit_workflow_does_not_pass_an_extras_flag_uv_audit_lacks() -> None:
    """`--all-extras` belongs to `uv export`, not `uv audit`, which includes
    optional dependencies by default and only offers `--no-extra`.

    A live run caught this: uv rejected the argument and exited 2, which the
    verdict script correctly refused to interpret. The fixture-driven tests
    could not have — they feed JSON directly and never build a command line.
    """
    text = AUDIT_WORKFLOW.read_text(encoding="utf-8")
    audit_lines = [line for line in text.splitlines() if "uv audit" in line and "#" not in line]
    assert audit_lines, "no `uv audit` invocation found"
    for line in audit_lines:
        assert "--all-extras" not in line, f"uv audit has no --all-extras: {line.strip()}"


def test_permission_check_rejects_a_workflow_missing_contents_read() -> None:
    with pytest.raises(AssertionError, match="contents: read"):
        assert_checkout_permission_declared(WORKFLOW_WITHOUT_CHECKOUT_PERMISSION)


def test_permission_check_is_not_satisfied_by_a_comment() -> None:
    """The real workflows explain the scope right above declaring it, so a
    substring search over the raw text passes on the explanation alone —
    measured by deleting the declaration and watching this file stay green."""
    with pytest.raises(AssertionError, match="contents: read"):
        assert_checkout_permission_declared(WORKFLOW_WITH_THE_PERMISSION_ONLY_IN_A_COMMENT)


def test_trigger_check_rejects_a_workflow_that_also_runs_on_pull_requests() -> None:
    with pytest.raises(AssertionError):
        assert_not_triggered_by_pull_requests(WORKFLOW_ALSO_RUNNING_ON_PULL_REQUESTS)
