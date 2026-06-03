"""Tests for mpg uninstall command (V-015 through V-030).

Mirrors test_setup.py. Verification IDs continue from V-014 to avoid collision.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from modern_python_guidance.setup_cmd import RULE_FILE_NAME
from modern_python_guidance.uninstall_cmd import (
    run_uninstall,
    uninstall_mcp,
    uninstall_rules,
    uninstall_skills,
)

BIN = [sys.executable, "-m", "modern_python_guidance"]

# Realistic output from `claude mcp remove <name> -s <scope>` when not present
# in that scope (exit 0). This is the per-scope idempotent "nothing here" case.
NOT_IN_SCOPE_OUT = b"No user-scoped MCP server found with name: mpg"
# Realistic output when a scope removal succeeds (exit 0).
REMOVED_OUT = b"File modified: /Users/x/.claude.json"


def _cp(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
    """Build a CompletedProcess for mocking subprocess.run."""
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


# --- uninstall_mcp ---


class TestUninstallMcp:
    """V-015 through V-019: MCP deregistration via per-scope enumeration."""

    def _patches(self):
        return (
            patch(
                "modern_python_guidance.uninstall_cmd.shutil.which",
                return_value="/usr/bin/claude",
            ),
            patch("modern_python_guidance.uninstall_cmd.subprocess.run"),
        )

    def test_success(self, capsys: pytest.CaptureFixture[str]):
        """V-015: server present in a scope is removed -> success."""
        which_p, run_p = self._patches()
        with which_p, run_p as mock_run:
            mock_run.return_value = _cp(0, stdout=REMOVED_OUT)
            ok = uninstall_mcp()
        assert ok is True
        assert "MCP server removed" in capsys.readouterr().out

    def test_not_registered_is_success(self, capsys: pytest.CaptureFixture[str]):
        """V-016: absent in every scope (exit 0 + 'No ...-scoped ... found') -> idempotent."""
        which_p, run_p = self._patches()
        with which_p, run_p as mock_run:
            mock_run.return_value = _cp(0, stderr=NOT_IN_SCOPE_OUT)
            ok = uninstall_mcp()
        assert ok is True
        assert "nothing to remove" in capsys.readouterr().out

    def test_dual_scope_both_removed(self):
        """multi-scope: removed from every scope in _REMOVE_SCOPES (no residue)."""
        which_p, run_p = self._patches()
        with which_p, run_p as mock_run:
            mock_run.return_value = _cp(0, stdout=REMOVED_OUT)
            uninstall_mcp()
        # One removal call per scope; each carries an explicit -s <scope>.
        scopes = {call.args[0][-1] for call in mock_run.call_args_list}
        assert scopes == {"local", "user"}
        for call in mock_run.call_args_list:
            assert "-s" in call.args[0]
            assert "--scope" not in call.args[0]

    def test_other_error_fails(self, capsys: pytest.CaptureFixture[str]):
        """V-017: a non-zero exit (not the not-found case) -> failure (do not hide)."""
        which_p, run_p = self._patches()
        with which_p, run_p as mock_run:
            mock_run.return_value = _cp(1, stderr=b"permission denied")
            ok = uninstall_mcp()
        assert ok is False
        err = capsys.readouterr().err
        assert "failed" in err
        assert "permission denied" in err

    def test_claude_not_found(self, capsys: pytest.CaptureFixture[str]):
        """V-018: claude missing -> failure + actionable (suggest --skills-only)."""
        with patch("modern_python_guidance.uninstall_cmd.shutil.which", return_value=None):
            ok = uninstall_mcp()
        assert ok is False
        err = capsys.readouterr().err
        assert "'claude' command not found" in err
        assert "--skills-only" in err

    def test_timeout(self, capsys: pytest.CaptureFixture[str]):
        """V-019: subprocess timeout -> failure."""
        with (
            patch(
                "modern_python_guidance.uninstall_cmd.shutil.which",
                return_value="/usr/bin/claude",
            ),
            patch(
                "modern_python_guidance.uninstall_cmd.subprocess.run",
                side_effect=subprocess.TimeoutExpired([], 30),
            ),
        ):
            ok = uninstall_mcp()
        assert ok is False
        assert "timed out" in capsys.readouterr().err

    def test_oserror_fails_gracefully(self, capsys: pytest.CaptureFixture[str]):
        """V-031: claude on PATH but unexecutable (OSError) -> failure, no traceback."""
        with (
            patch(
                "modern_python_guidance.uninstall_cmd.shutil.which",
                return_value="/usr/bin/claude",
            ),
            patch(
                "modern_python_guidance.uninstall_cmd.subprocess.run",
                side_effect=OSError("Exec format error"),
            ),
        ):
            ok = uninstall_mcp()
        assert ok is False
        assert "failed to run" in capsys.readouterr().err

    def test_dry_run(self, capsys: pytest.CaptureFixture[str]):
        """dry-run does not invoke subprocess; lists a remove per scope."""
        which_p, run_p = self._patches()
        with which_p, run_p as mock_run:
            ok = uninstall_mcp(dry_run=True)
        assert ok is True
        assert mock_run.call_count == 0
        out = capsys.readouterr().out
        assert "Would run" in out
        assert "-s local" in out
        assert "-s user" in out


# --- uninstall_skills ---


class TestUninstallSkills:
    """V-020 through V-024, V-028: symlink removal safety."""

    def _make_source(self, tmp_path: Path) -> Path:
        source = tmp_path / "pkg_skills" / "modern-python-guidance"
        source.mkdir(parents=True)
        (source / "SKILL.md").touch()
        return source

    def _link(self, project: Path) -> Path:
        return project / ".claude" / "skills" / "modern-python-guidance"

    def test_removes_symlink_target_survives(self, tmp_path: Path, capsys):
        """V-020 + A-003: link is removed; the symlink TARGET (and its files) survive."""
        source = self._make_source(tmp_path)
        project = tmp_path / "project"
        link = self._link(project)
        link.parent.mkdir(parents=True)
        os.symlink(source, link)

        ok = uninstall_skills(project_dir=project)

        assert ok is True
        assert not link.is_symlink()
        assert not link.exists()
        # Critical: target directory and its contents must NOT be deleted.
        assert source.is_dir()
        assert (source / "SKILL.md").exists()
        assert "unlinked" in capsys.readouterr().out

    def test_absent_is_success(self, tmp_path: Path, capsys):
        """V-021: no symlink present -> idempotent no-op success."""
        project = tmp_path / "project"
        project.mkdir()
        ok = uninstall_skills(project_dir=project)
        assert ok is True
        assert "nothing to remove" in capsys.readouterr().out

    def test_broken_symlink_removed(self, tmp_path: Path):
        """V-022: dangling symlink (target gone) is still removed."""
        project = tmp_path / "project"
        link = self._link(project)
        link.parent.mkdir(parents=True)
        os.symlink(tmp_path / "nonexistent", link)
        assert link.is_symlink()
        assert not link.exists()

        ok = uninstall_skills(project_dir=project)

        assert ok is True
        assert not link.is_symlink()

    def test_non_symlink_refused(self, tmp_path: Path, capsys):
        """V-023: a real dir/file at the link path is refused, NOT deleted."""
        project = tmp_path / "project"
        blocker = self._link(project)
        blocker.mkdir(parents=True)
        (blocker / "important.txt").write_text("user data")

        ok = uninstall_skills(project_dir=project)

        assert ok is False
        err = capsys.readouterr().err
        assert "not a symlink" in err
        # The real entity and its contents must survive.
        assert blocker.is_dir()
        assert (blocker / "important.txt").read_text() == "user data"

    def test_works_without_source(self, tmp_path: Path):
        """V-024: uninstall must NOT depend on the bundled skills source existing."""
        # Point the symlink at a source, then delete the source -> dangling.
        source = self._make_source(tmp_path)
        project = tmp_path / "project"
        link = self._link(project)
        link.parent.mkdir(parents=True)
        os.symlink(source, link)
        import shutil as _sh

        _sh.rmtree(source)  # source gone; link now dangling

        # _find_skills_dir must never be consulted; even if it raised, this must pass.
        ok = uninstall_skills(project_dir=project)
        assert ok is True
        assert not link.is_symlink()

    def test_dry_run_no_side_effects(self, tmp_path: Path, capsys):
        """V-025: dry-run reports but does not remove."""
        source = self._make_source(tmp_path)
        project = tmp_path / "project"
        link = self._link(project)
        link.parent.mkdir(parents=True)
        os.symlink(source, link)

        ok = uninstall_skills(project_dir=project, dry_run=True)

        assert ok is True
        assert link.is_symlink()  # still there
        assert "Would remove" in capsys.readouterr().out

    def test_resolves_correct_root_not_distant_ancestor(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """V-009: uninstall resolves nearest project root, not distant ancestor."""
        home = tmp_path / "home"
        (home / ".claude" / "skills" / "modern-python-guidance").mkdir(parents=True)
        repo = home / "projects" / "repo"
        repo.mkdir(parents=True)
        (repo / ".git").mkdir()
        link = repo / ".claude" / "skills" / "modern-python-guidance"
        link.parent.mkdir(parents=True)
        os.symlink(tmp_path / "pkg_skills", link)

        monkeypatch.chdir(repo)
        ok = uninstall_skills()

        assert ok is True
        assert not link.is_symlink()
        # Home-level skills dir must be untouched
        assert (home / ".claude" / "skills" / "modern-python-guidance").is_dir()

    def test_non_symlink_path_quoted(self, tmp_path: Path, capsys):
        """V-028: rm hint uses shell-safe quoting for paths with spaces."""
        project = tmp_path / "my project"
        blocker = self._link(project)
        blocker.mkdir(parents=True)

        uninstall_skills(project_dir=project)

        err = capsys.readouterr().err
        assert "'" in err or '"' in err


# --- uninstall_rules ---


class TestUninstallRules:
    """V-049 through V-055: rule symlink removal."""

    def _make_source(self, tmp_path: Path) -> Path:
        source = tmp_path / "pkg_rules" / RULE_FILE_NAME
        source.parent.mkdir(parents=True)
        source.write_text("---\npaths: ['**/*.py']\n---\n# Test\n")
        return source

    def _link(self, project: Path) -> Path:
        return project / ".claude" / "rules" / RULE_FILE_NAME

    def test_removes_symlink(self, tmp_path: Path, capsys):
        """V-049: symlink is removed; target survives."""
        source = self._make_source(tmp_path)
        project = tmp_path / "project"
        link = self._link(project)
        link.parent.mkdir(parents=True)
        os.symlink(source, link)

        ok = uninstall_rules(project_dir=project)

        assert ok is True
        assert not link.is_symlink()
        assert not link.exists()
        assert source.is_file()
        assert "unlinked" in capsys.readouterr().out

    def test_absent_is_success(self, tmp_path: Path, capsys):
        """V-050: no symlink present -> idempotent no-op success."""
        project = tmp_path / "project"
        project.mkdir()
        ok = uninstall_rules(project_dir=project)
        assert ok is True
        assert "nothing to remove" in capsys.readouterr().out

    def test_non_symlink_refused(self, tmp_path: Path, capsys):
        """V-051: regular file at path is refused."""
        project = tmp_path / "project"
        blocker = self._link(project)
        blocker.parent.mkdir(parents=True)
        blocker.write_text("user content")

        ok = uninstall_rules(project_dir=project)

        assert ok is False
        err = capsys.readouterr().err
        assert "not a symlink" in err
        assert blocker.read_text() == "user content"

    def test_dry_run(self, tmp_path: Path, capsys):
        """V-052: dry-run does not remove."""
        source = self._make_source(tmp_path)
        project = tmp_path / "project"
        link = self._link(project)
        link.parent.mkdir(parents=True)
        os.symlink(source, link)

        ok = uninstall_rules(project_dir=project, dry_run=True)

        assert ok is True
        assert link.is_symlink()
        assert "Would remove" in capsys.readouterr().out

    def test_broken_symlink_removed(self, tmp_path: Path):
        """Dangling symlink (target gone) is still removed."""
        project = tmp_path / "project"
        link = self._link(project)
        link.parent.mkdir(parents=True)
        os.symlink(tmp_path / "nonexistent", link)

        ok = uninstall_rules(project_dir=project)

        assert ok is True
        assert not link.is_symlink()


# --- run_uninstall (orchestrator) ---


class TestRunUninstall:
    """V-026, V-027, V-053~V-055: exit codes, partial success, mutual exclusion."""

    def _patch_all(self, mcp=True, skills=True, rules=True):
        return (
            patch("modern_python_guidance.uninstall_cmd.uninstall_mcp", return_value=mcp),
            patch("modern_python_guidance.uninstall_cmd.uninstall_skills", return_value=skills),
            patch("modern_python_guidance.uninstall_cmd.uninstall_rules", return_value=rules),
        )

    def test_full_success(self):
        """V-053: exit 0 on full success (MCP + Skills + Rules)."""
        p_mcp, p_skills, p_rules = self._patch_all()
        with p_mcp, p_skills, p_rules:
            assert run_uninstall() == 0

    def test_mcp_only(self):
        """V-054: --mcp-only skips Skills and Rules."""
        p_mcp, p_skills, p_rules = self._patch_all()
        with p_mcp as m_mcp, p_skills as m_skills, p_rules as m_rules:
            assert run_uninstall(mcp_only=True) == 0
            m_mcp.assert_called_once()
            m_skills.assert_not_called()
            m_rules.assert_not_called()

    def test_skills_only(self):
        """V-055: --skills-only includes Rules but skips MCP."""
        p_mcp, p_skills, p_rules = self._patch_all()
        with p_mcp as m_mcp, p_skills as m_skills, p_rules as m_rules:
            assert run_uninstall(skills_only=True) == 0
            m_mcp.assert_not_called()
            m_skills.assert_called_once()
            m_rules.assert_called_once()

    def test_partial_mcp_fail(self):
        """V-026: MCP fails but Skills+Rules succeed -> exit 1."""
        p_mcp, p_skills, p_rules = self._patch_all(mcp=False)
        with p_mcp, p_skills, p_rules:
            assert run_uninstall() == 1

    def test_partial_skills_fail(self):
        """V-026: MCP+Rules ok, Skills fails -> exit 1."""
        p_mcp, p_skills, p_rules = self._patch_all(skills=False)
        with p_mcp, p_skills, p_rules:
            assert run_uninstall() == 1

    def test_partial_rules_fail(self):
        """Rules fails, others ok -> exit 1."""
        p_mcp, p_skills, p_rules = self._patch_all(rules=False)
        with p_mcp, p_skills, p_rules:
            assert run_uninstall() == 1

    def test_full_failure(self):
        p_mcp, p_skills, p_rules = self._patch_all(mcp=False, skills=False, rules=False)
        with p_mcp, p_skills, p_rules:
            assert run_uninstall() == 1

    def test_dry_run_no_done_message(self, capsys: pytest.CaptureFixture[str]):
        p_mcp, p_skills, p_rules = self._patch_all()
        with p_mcp, p_skills, p_rules:
            assert run_uninstall(dry_run=True) == 0
        assert "Done" not in capsys.readouterr().out

    def test_mutual_exclusion(self, capsys: pytest.CaptureFixture[str]):
        """V-027: --mcp-only and --skills-only together -> error exit 1."""
        code = run_uninstall(mcp_only=True, skills_only=True)
        assert code == 1
        assert "mutually exclusive" in capsys.readouterr().err


# --- CLI integration ---


class TestCliIntegration:
    """V-029, V-030."""

    def test_uninstall_help_has_no_scope(self):
        """V-029: --help lists the flags but NOT --scope (auto-detect)."""
        r = subprocess.run(
            [*BIN, "uninstall", "--help"], capture_output=True, text=True, timeout=10
        )
        assert r.returncode == 0
        assert "--mcp-only" in r.stdout
        assert "--skills-only" in r.stdout
        assert "--project-dir" in r.stdout
        assert "--dry-run" in r.stdout
        assert "--scope" not in r.stdout

    def test_uninstall_dry_run_skills_only(self):
        """V-030: --skills-only --dry-run smoke test (no real removal)."""
        r = subprocess.run(
            [*BIN, "uninstall", "--skills-only", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert r.returncode == 0

    def test_uninstall_mutual_exclusion_cli(self):
        """V-030: --mcp-only and --skills-only together errors at CLI level."""
        r = subprocess.run(
            [*BIN, "uninstall", "--mcp-only", "--skills-only", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert r.returncode != 0
        assert "mutually exclusive" in r.stderr
