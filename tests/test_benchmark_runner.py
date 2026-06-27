"""Tests for the V5 benchmark runner safety affordances."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "bench" / "run-v5.sh"


def run_v5(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(RUNNER), *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_non_dry_run_requires_explicit_credit_use_opt_in(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:/bin:/usr/bin"

    proc = run_v5("testrun", "control", "--variant", "a", "--granularity", "normal", env=env)

    assert proc.returncode == 2
    assert "--allow-credit-use" in proc.stderr
    assert "may consume Claude credits" in proc.stderr
    assert "claude CLI not found" not in proc.stderr


def test_dry_run_warns_about_credit_use_without_requiring_opt_in() -> None:
    proc = run_v5(
        "testrun",
        "both",
        "--variant",
        "a",
        "--granularity",
        "normal",
        "-N",
        "1",
        "--dry-run",
    )

    assert proc.returncode == 0
    assert "Credit use:   none (--dry-run)" in proc.stdout
    assert "--allow-credit-use" in proc.stdout
