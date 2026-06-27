"""Regression tests for release artifact verification in CI."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


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
