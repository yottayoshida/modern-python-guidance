"""Regression tests for release artifact verification in CI."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CI_WORKFLOW = WORKFLOWS / "ci.yml"


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


# --- nothing keeps producing work after maintenance stopped ---

GITHUB_DIR = REPO_ROOT / ".github"

# Each of these would, in a repository nobody maintains any more, keep filing
# issues or pull requests, or keep running on a timer, with nobody to answer.
_AUTOMATION = (
    (re.compile(r"^\s*schedule\s*:", re.MULTILINE), "runs on a schedule"),
    (re.compile(r"\bissues\s*:\s*write\b"), "can open issues"),
    (re.compile(r"\bpull-requests\s*:\s*write\b"), "can open pull requests"),
    (re.compile(r"\bwrite-all\b"), "grants every write scope"),
)


def automation_findings(github_dir: Path) -> list[str]:
    """What under `github_dir` would keep producing work, one line per finding.

    Comment lines are dropped first: a commented-out trigger does not run.
    Finding no workflow at all is an error rather than a clean result — "none
    of zero files schedules anything" is true of a moved directory too.
    """
    workflow_dir = github_dir / "workflows"
    workflows = sorted([*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")])
    assert workflows, f"no workflow under {workflow_dir}; this check does not apply"

    findings = []
    for workflow in workflows:
        text = "\n".join(
            line
            for line in workflow.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        findings.extend(
            f"{workflow.name} {what}" for pattern, what in _AUTOMATION if pattern.search(text)
        )
    findings.extend(
        f"{name} opens pull requests"
        for name in ("dependabot.yml", "dependabot.yaml")
        if (github_dir / name).exists()
    )
    return findings


def test_no_automation_outlives_maintenance() -> None:
    """The README says the project is no longer maintained, so nothing here
    may run on a timer or file issues and pull requests."""
    assert automation_findings(GITHUB_DIR) == []


CLEAN_WORKFLOW = """
name: CI

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    steps:
      - run: echo hi
"""


def github_dir_with(tmp_path: Path, extra: str | None = None) -> Path:
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "ci.yml").write_text(CLEAN_WORKFLOW, encoding="utf-8")
    if extra is not None:
        (workflows / "extra.yaml").write_text("name: Extra\n" + extra, encoding="utf-8")
    return tmp_path


def test_automation_check_passes_a_clean_tree(tmp_path: Path) -> None:
    assert automation_findings(github_dir_with(tmp_path)) == []


@pytest.mark.parametrize(
    ("extra", "reason"),
    [
        ("on:\n  schedule:\n    - cron: '0 9 * * 1'\n", "runs on a schedule"),
        ("permissions:\n  issues: write\n", "can open issues"),
        ("permissions:\n  pull-requests: write\n", "can open pull requests"),
        ("permissions: write-all\n", "grants every write scope"),
    ],
    ids=["schedule", "issues-write", "pull-requests-write", "write-all"],
)
def test_automation_check_names_each_kind(tmp_path: Path, extra: str, reason: str) -> None:
    """One violation per case, in a `.yaml` file, so each pattern and the
    second extension are exercised on their own."""
    assert automation_findings(github_dir_with(tmp_path, extra)) == [f"extra.yaml {reason}"]


@pytest.mark.parametrize("name", ["dependabot.yml", "dependabot.yaml"])
def test_automation_check_names_a_dependabot_config(tmp_path: Path, name: str) -> None:
    github = github_dir_with(tmp_path)
    (github / name).write_text("version: 2\n", encoding="utf-8")
    assert automation_findings(github) == [f"{name} opens pull requests"]


def test_automation_check_ignores_a_commented_out_trigger(tmp_path: Path) -> None:
    """The permission line is the one that needs the comment stripped: the
    schedule pattern is anchored at the key, which a `#` already moves."""
    extra = (
        "on:\n  # schedule:\n  #   - cron: '0 9 * * 1'\n  workflow_dispatch:\n"
        "\npermissions:\n  contents: read\n  # issues: write\n"
    )
    assert automation_findings(github_dir_with(tmp_path, extra)) == []


def test_automation_check_refuses_a_directory_without_workflows(tmp_path: Path) -> None:
    (tmp_path / "workflows").mkdir()
    with pytest.raises(AssertionError, match="no workflow"):
        automation_findings(tmp_path)
