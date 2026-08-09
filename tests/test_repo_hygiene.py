"""What this repository ignores and what it lints, asked of the tools themselves.

A pattern appearing in a config file and a path actually being treated that way
are different claims — a trailing slash, an anchor, or an earlier negation can
separate them. So these run `git check-ignore` and `ruff --show-files` rather
than grepping `.gitignore` and `pyproject.toml`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Generated or personal paths that appear during ordinary development. Each one
# left untracked shows up in `git status` and blocks tooling that refuses to run
# against a dirty tree.
IGNORED_PATHS = [
    ".coverage",
    "uv.lock",
    ".claude/skills/modern-python-guidance",
    ".claude/rules/modern-python.md",
    ".claude/settings.local.json",
    ".claude/agent-memory/architect/notes.md",
]

# Paths that must stay visible. Ignoring `.claude/` wholesale would hide these,
# which is the failure this list exists to catch.
TRACKED_PATHS = [
    "pyproject.toml",
    "README.md",
    "src/modern_python_guidance/cli.py",
    ".claude/commands/example.md",
    ".github/workflows/ci.yml",
]


def _is_ignored(relative_path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", relative_path],
        cwd=REPO_ROOT,
        capture_output=True,
        timeout=10,
    )
    if result.returncode not in (0, 1):
        pytest.fail(f"git check-ignore failed for {relative_path}: {result.stderr!r}")
    return result.returncode == 0


@pytest.mark.parametrize("relative_path", IGNORED_PATHS)
def test_generated_and_personal_paths_are_ignored(relative_path: str) -> None:
    assert _is_ignored(relative_path), f"{relative_path} would show up as untracked"


@pytest.mark.parametrize("relative_path", TRACKED_PATHS)
def test_project_content_is_not_ignored(relative_path: str) -> None:
    assert not _is_ignored(relative_path), f"{relative_path} is hidden from git"


def _ruff(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ruff", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_lint_passes_from_the_repository_root() -> None:
    """`ruff check .` is what a contributor types before reading any config."""
    result = _ruff("check", ".")
    assert result.returncode == 0, result.stdout or result.stderr


def test_lint_skips_fixtures_but_keeps_the_bench_tooling() -> None:
    """The exclusion is narrow: benchmark inputs only, not everything under bench/.

    `--show-files` prints absolute paths, so these are compared after making
    them relative — a substring test would pass against paths that merely end
    the same way.
    """
    result = _ruff("check", "--show-files", ".")
    assert result.returncode == 0, result.stderr

    checked = set()
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            checked.add(Path(line.strip()).relative_to(REPO_ROOT).as_posix())
        except ValueError:  # outside the repository; not ours to reason about
            continue

    assert checked, "ruff reported no files at all"
    assert "bench/score_v5.py" in checked, "bench tooling dropped out of linting"
    fixtures = sorted(p for p in checked if p.startswith("bench/fixtures/"))
    assert not fixtures, f"fixtures are still linted: {fixtures[:3]}"
