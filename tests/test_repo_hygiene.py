"""The repository's own ignore rules, checked through git rather than by reading them.

A pattern present in `.gitignore` and a path actually ignored are different
claims — a trailing slash, an anchor, or an earlier negation can separate them —
so these ask `git check-ignore` instead of grepping the file.
"""

from __future__ import annotations

import subprocess
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
