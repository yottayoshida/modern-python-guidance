"""Tests for mpg setup command (V-001 through V-014)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from modern_python_guidance.setup_cmd import (
    RULE_FILE_NAME,
    _find_project_root,
    _find_rule_source,
    _find_skills_dir,
    run_setup,
    setup_mcp,
    setup_rules,
    setup_skills,
)

BIN = [sys.executable, "-m", "modern_python_guidance"]


# --- _find_skills_dir ---


class TestFindSkillsDir:
    """V-005 / V-006: skills path resolution for installed and editable installs."""

    def test_returns_existing_dir(self):
        result = _find_skills_dir()
        assert result.is_dir()
        assert result.name == "modern-python-guidance"
        assert (result / "SKILL.md").exists() or (result / "guides").is_dir()


# --- _find_project_root ---


class TestFindProjectRoot:
    def test_finds_claude_dir(self, tmp_path: Path):
        (tmp_path / ".claude").mkdir()
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        assert _find_project_root(sub) == tmp_path

    def test_finds_git_dir(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "src"
        sub.mkdir()
        assert _find_project_root(sub) == tmp_path

    def test_finds_pyproject(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").touch()
        sub = tmp_path / "deep" / "nest"
        sub.mkdir(parents=True)
        assert _find_project_root(sub) == tmp_path

    def test_nearest_marker_wins(self, tmp_path: Path):
        """Nearest ancestor with any marker wins over distant ancestor."""
        (tmp_path / ".claude").mkdir()
        child = tmp_path / "child"
        child.mkdir()
        (child / ".git").mkdir()
        assert _find_project_root(child) == child

    def test_bug_repro_home_claude_escapes(self, tmp_path: Path):
        """V-001: .claude at home + .git at repo -> repo wins, not home."""
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        repo = home / "projects" / "repo"
        repo.mkdir(parents=True)
        (repo / ".git").mkdir()
        src = repo / "src"
        src.mkdir()
        assert _find_project_root(src) == repo

    def test_git_as_file(self, tmp_path: Path):
        """V-008: .git as a file (worktree/submodule) is detected."""
        (tmp_path / ".git").write_text("gitdir: /some/other/path")
        sub = tmp_path / "src"
        sub.mkdir()
        assert _find_project_root(sub) == tmp_path

    def test_falls_back_to_cwd(self, tmp_path: Path):
        bare = tmp_path / "empty"
        bare.mkdir()
        result = _find_project_root(bare)
        assert result == bare


# --- setup_mcp ---


class TestSetupMcp:
    """V-001, V-002: MCP registration tests."""

    def test_claude_not_found(self, capsys: pytest.CaptureFixture[str]):
        """V-001: actionable error when claude is missing."""
        with patch("modern_python_guidance.setup_cmd.shutil.which", return_value=None):
            ok = setup_mcp()
        assert ok is False
        err = capsys.readouterr().err
        assert "'claude' command not found" in err
        assert "--skills-only" in err

    def test_success(self, capsys: pytest.CaptureFixture[str]):
        """V-002: successful MCP registration."""
        with (
            patch("modern_python_guidance.setup_cmd.shutil.which", return_value="/usr/bin/claude"),
            patch("modern_python_guidance.setup_cmd.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            ok = setup_mcp(scope="user")
        assert ok is True
        out = capsys.readouterr().out
        assert "MCP server registered" in out
        assert "user scope" in out

    def test_idempotent(self):
        """V-002: running twice does not error."""
        with (
            patch("modern_python_guidance.setup_cmd.shutil.which", return_value="/usr/bin/claude"),
            patch("modern_python_guidance.setup_cmd.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            assert setup_mcp() is True
            assert setup_mcp() is True

    def test_timeout(self, capsys: pytest.CaptureFixture[str]):
        with (
            patch("modern_python_guidance.setup_cmd.shutil.which", return_value="/usr/bin/claude"),
            patch(
                "modern_python_guidance.setup_cmd.subprocess.run",
                side_effect=subprocess.TimeoutExpired([], 30),
            ),
        ):
            ok = setup_mcp()
        assert ok is False
        assert "timed out" in capsys.readouterr().err

    def test_failure_exit_code(self, capsys: pytest.CaptureFixture[str]):
        with (
            patch("modern_python_guidance.setup_cmd.shutil.which", return_value="/usr/bin/claude"),
            patch("modern_python_guidance.setup_cmd.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess([], 1, stderr=b"fail")
            ok = setup_mcp()
        assert ok is False
        assert "failed" in capsys.readouterr().err

    def test_oserror_fails_gracefully(self, capsys: pytest.CaptureFixture[str]):
        """V-036: claude on PATH but unexecutable (OSError) -> failure, no traceback."""
        with (
            patch(
                "modern_python_guidance.setup_cmd.shutil.which",
                return_value="/usr/bin/claude",
            ),
            patch(
                "modern_python_guidance.setup_cmd.subprocess.run",
                side_effect=OSError("Exec format error"),
            ),
        ):
            ok = setup_mcp()
        assert ok is False
        assert "failed to run" in capsys.readouterr().err

    def test_dry_run(self, capsys: pytest.CaptureFixture[str]):
        """V-010: dry-run does not invoke subprocess."""
        with (
            patch("modern_python_guidance.setup_cmd.shutil.which", return_value="/usr/bin/claude"),
            patch("modern_python_guidance.setup_cmd.subprocess.run") as mock_run,
        ):
            ok = setup_mcp(dry_run=True)
        assert ok is True
        assert mock_run.call_count == 0
        assert "Would run" in capsys.readouterr().out

    def test_dry_run_without_claude(self, capsys: pytest.CaptureFixture[str]):
        """dry-run succeeds even when claude is not installed."""
        with patch("modern_python_guidance.setup_cmd.shutil.which", return_value=None):
            ok = setup_mcp(dry_run=True)
        assert ok is True
        out = capsys.readouterr().out
        assert "Would run" in out
        assert "claude" in out

    def test_dry_run_argv_shape(self, capsys: pytest.CaptureFixture[str]):
        """dry-run output contains expected subprocess argv components."""
        mock_which = "modern_python_guidance.setup_cmd.shutil.which"
        with patch(mock_which, return_value="/usr/bin/claude"):
            setup_mcp(scope="local", dry_run=True)
        out = capsys.readouterr().out
        assert "mcp add" in out
        assert "--scope local" in out
        assert "mpg mcp" in out

    def test_subprocess_argv(self):
        """Actual subprocess.run receives correct argv list."""
        with (
            patch("modern_python_guidance.setup_cmd.shutil.which", return_value="/usr/bin/claude"),
            patch("modern_python_guidance.setup_cmd.subprocess.run") as m,
        ):
            m.return_value = subprocess.CompletedProcess([], 0)
            setup_mcp(scope="local")
        argv = m.call_args[0][0]
        assert argv == [
            "/usr/bin/claude",
            "mcp",
            "add",
            "--scope",
            "local",
            "mpg",
            "--",
            "mpg",
            "mcp",
        ]


# --- setup_skills ---


class TestSetupSkills:
    """V-003, V-004, V-011: symlink creation tests."""

    def _make_source(self, tmp_path: Path) -> Path:
        source = tmp_path / "pkg_skills" / "modern-python-guidance"
        source.mkdir(parents=True)
        (source / "SKILL.md").touch()
        return source

    def test_creates_symlink(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """V-003: creates .claude/skills/ and symlink."""
        source = self._make_source(tmp_path)
        project = tmp_path / "project"
        project.mkdir()

        with patch("modern_python_guidance.setup_cmd._find_skills_dir", return_value=source):
            ok = setup_skills(project_dir=project)

        assert ok is True
        link = project / ".claude" / "skills" / "modern-python-guidance"
        assert link.is_symlink()
        assert link.resolve() == source.resolve()
        assert "Agent Skills linked" in capsys.readouterr().out

    def test_correct_symlink_skips(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """V-004: existing correct symlink is skipped."""
        source = self._make_source(tmp_path)
        project = tmp_path / "project"
        link = project / ".claude" / "skills" / "modern-python-guidance"
        link.parent.mkdir(parents=True)
        os.symlink(source, link)

        with patch("modern_python_guidance.setup_cmd._find_skills_dir", return_value=source):
            ok = setup_skills(project_dir=project)

        assert ok is True
        assert "already linked" in capsys.readouterr().out

    def test_stale_symlink_replaced(self, tmp_path: Path):
        """V-004: stale symlink pointing to wrong target is replaced."""
        source = self._make_source(tmp_path)
        old_target = tmp_path / "old_skills"
        old_target.mkdir()
        project = tmp_path / "project"
        link = project / ".claude" / "skills" / "modern-python-guidance"
        link.parent.mkdir(parents=True)
        os.symlink(old_target, link)

        with patch("modern_python_guidance.setup_cmd._find_skills_dir", return_value=source):
            ok = setup_skills(project_dir=project)

        assert ok is True
        assert link.resolve() == source.resolve()

    def test_broken_symlink_replaced(self, tmp_path: Path):
        """V-011: dangling symlink is replaced."""
        source = self._make_source(tmp_path)
        project = tmp_path / "project"
        link = project / ".claude" / "skills" / "modern-python-guidance"
        link.parent.mkdir(parents=True)
        os.symlink(tmp_path / "nonexistent", link)
        assert link.is_symlink()
        assert not link.exists()

        with patch("modern_python_guidance.setup_cmd._find_skills_dir", return_value=source):
            ok = setup_skills(project_dir=project)

        assert ok is True
        assert link.resolve() == source.resolve()

    def test_non_symlink_blocker(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """V-004: regular file/dir at link path produces error."""
        source = self._make_source(tmp_path)
        project = tmp_path / "project"
        blocker = project / ".claude" / "skills" / "modern-python-guidance"
        blocker.mkdir(parents=True)
        (blocker / "file.txt").touch()

        with patch("modern_python_guidance.setup_cmd._find_skills_dir", return_value=source):
            ok = setup_skills(project_dir=project)

        assert ok is False
        err = capsys.readouterr().err
        assert "not a symlink" in err
        assert "rm -rf" in err

    def test_non_symlink_blocker_path_quoted(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ):
        """rm -rf hint uses shell-safe quoting for paths with spaces."""
        source = self._make_source(tmp_path)
        project = tmp_path / "my project"
        blocker = project / ".claude" / "skills" / "modern-python-guidance"
        blocker.mkdir(parents=True)

        with patch("modern_python_guidance.setup_cmd._find_skills_dir", return_value=source):
            setup_skills(project_dir=project)

        err = capsys.readouterr().err
        assert "'" in err or '"' in err

    def test_autodetect_avoids_home_escape(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """setup_skills auto-discovers repo root, not distant ~/.claude."""
        source = self._make_source(tmp_path)
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        repo = home / "projects" / "repo"
        repo.mkdir(parents=True)
        (repo / ".git").mkdir()

        monkeypatch.chdir(repo)
        with patch("modern_python_guidance.setup_cmd._find_skills_dir", return_value=source):
            ok = setup_skills()

        assert ok is True
        link = repo / ".claude" / "skills" / "modern-python-guidance"
        assert link.is_symlink()
        assert not (home / ".claude" / "skills" / "modern-python-guidance").exists()

    def test_dry_run(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """V-010: dry-run does not create symlink."""
        source = self._make_source(tmp_path)
        project = tmp_path / "project"
        project.mkdir()

        with patch("modern_python_guidance.setup_cmd._find_skills_dir", return_value=source):
            ok = setup_skills(project_dir=project, dry_run=True)

        assert ok is True
        link = project / ".claude" / "skills" / "modern-python-guidance"
        assert not link.exists()
        assert "Would link" in capsys.readouterr().out


# --- _find_rule_source ---


class TestFindRuleSource:
    def test_returns_existing_file(self):
        result = _find_rule_source()
        assert result.is_file()
        assert result.name == RULE_FILE_NAME


# --- setup_rules ---


class TestSetupRules:
    """V-037 through V-048: rule symlink creation tests."""

    def _make_source(self, tmp_path: Path) -> Path:
        source = tmp_path / "pkg_rules" / RULE_FILE_NAME
        source.parent.mkdir(parents=True)
        source.write_text("---\npaths: ['**/*.py']\n---\n# Test\n")
        return source

    def test_creates_symlink(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """V-037: creates .claude/rules/ and symlink."""
        source = self._make_source(tmp_path)
        project = tmp_path / "project"
        project.mkdir()

        with patch("modern_python_guidance.setup_cmd._find_rule_source", return_value=source):
            ok = setup_rules(project_dir=project)

        assert ok is True
        link = project / ".claude" / "rules" / RULE_FILE_NAME
        assert link.is_symlink()
        assert "Rule linked" in capsys.readouterr().out

    def test_symlink_target_resolves(self, tmp_path: Path):
        """V-038: symlink target resolves to the bundled rule file."""
        source = self._make_source(tmp_path)
        project = tmp_path / "project"
        project.mkdir()

        with patch("modern_python_guidance.setup_cmd._find_rule_source", return_value=source):
            setup_rules(project_dir=project)

        link = project / ".claude" / "rules" / RULE_FILE_NAME
        assert link.resolve() == source.resolve()

    def test_creates_rules_dir(self, tmp_path: Path):
        """V-039: creates .claude/rules/ directory if absent."""
        source = self._make_source(tmp_path)
        project = tmp_path / "project"
        project.mkdir()
        assert not (project / ".claude" / "rules").exists()

        with patch("modern_python_guidance.setup_cmd._find_rule_source", return_value=source):
            setup_rules(project_dir=project)

        assert (project / ".claude" / "rules").is_dir()

    def test_correct_symlink_skips(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """V-040: existing correct symlink is skipped (idempotent)."""
        source = self._make_source(tmp_path)
        project = tmp_path / "project"
        link = project / ".claude" / "rules" / RULE_FILE_NAME
        link.parent.mkdir(parents=True)
        os.symlink(source, link)

        with patch("modern_python_guidance.setup_cmd._find_rule_source", return_value=source):
            ok = setup_rules(project_dir=project)

        assert ok is True
        assert "already linked" in capsys.readouterr().out

    def test_stale_symlink_replaced(self, tmp_path: Path):
        """V-041: stale symlink pointing to wrong target is replaced."""
        source = self._make_source(tmp_path)
        old = tmp_path / "old_rule.md"
        old.touch()
        project = tmp_path / "project"
        link = project / ".claude" / "rules" / RULE_FILE_NAME
        link.parent.mkdir(parents=True)
        os.symlink(old, link)

        with patch("modern_python_guidance.setup_cmd._find_rule_source", return_value=source):
            ok = setup_rules(project_dir=project)

        assert ok is True
        assert link.resolve() == source.resolve()

    def test_broken_symlink_replaced(self, tmp_path: Path):
        """V-042: broken (dangling) symlink is replaced."""
        source = self._make_source(tmp_path)
        project = tmp_path / "project"
        link = project / ".claude" / "rules" / RULE_FILE_NAME
        link.parent.mkdir(parents=True)
        os.symlink(tmp_path / "nonexistent", link)
        assert link.is_symlink()
        assert not link.exists()

        with patch("modern_python_guidance.setup_cmd._find_rule_source", return_value=source):
            ok = setup_rules(project_dir=project)

        assert ok is True
        assert link.resolve() == source.resolve()

    def test_non_symlink_blocker(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """V-043: non-symlink file at path produces error."""
        source = self._make_source(tmp_path)
        project = tmp_path / "project"
        blocker = project / ".claude" / "rules" / RULE_FILE_NAME
        blocker.parent.mkdir(parents=True)
        blocker.write_text("user content")

        with patch("modern_python_guidance.setup_cmd._find_rule_source", return_value=source):
            ok = setup_rules(project_dir=project)

        assert ok is False
        err = capsys.readouterr().err
        assert "not a symlink" in err
        assert "rm " in err

    def test_dry_run(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """V-044: dry-run does not create symlink."""
        source = self._make_source(tmp_path)
        project = tmp_path / "project"
        project.mkdir()

        with patch("modern_python_guidance.setup_cmd._find_rule_source", return_value=source):
            ok = setup_rules(project_dir=project, dry_run=True)

        assert ok is True
        link = project / ".claude" / "rules" / RULE_FILE_NAME
        assert not link.exists()
        assert "Would link" in capsys.readouterr().out

    def test_symlink_source_refused(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """Security: source that is itself a symlink is refused."""
        real = self._make_source(tmp_path)
        fake_source = tmp_path / "symlink_source.md"
        os.symlink(real, fake_source)
        project = tmp_path / "project"
        project.mkdir()

        with patch("modern_python_guidance.setup_cmd._find_rule_source", return_value=fake_source):
            ok = setup_rules(project_dir=project)

        assert ok is False
        assert "itself a symlink" in capsys.readouterr().err


# --- run_setup (orchestrator) ---


class TestRunSetup:
    """V-012, V-013, V-014, V-045~V-048, V-058~V-060: exit codes and partial success."""

    def _patch_all(self, mcp=True, skills=True, rules=True):
        return (
            patch("modern_python_guidance.setup_cmd.setup_mcp", return_value=mcp),
            patch("modern_python_guidance.setup_cmd.setup_skills", return_value=skills),
            patch("modern_python_guidance.setup_cmd.setup_rules", return_value=rules),
        )

    def test_full_success(self):
        """V-012 / V-045: exit 0 on full success (MCP + Skills + Rules)."""
        p_mcp, p_skills, p_rules = self._patch_all()
        with p_mcp, p_skills, p_rules:
            assert run_setup() == 0

    def test_mcp_only(self):
        """V-046: --mcp-only skips Skills and Rules."""
        p_mcp, p_skills, p_rules = self._patch_all()
        with p_mcp as m_mcp, p_skills as m_skills, p_rules as m_rules:
            assert run_setup(mcp_only=True) == 0
            m_mcp.assert_called_once()
            m_skills.assert_not_called()
            m_rules.assert_not_called()

    def test_skills_only(self):
        """V-047: --skills-only includes Rules but skips MCP."""
        p_mcp, p_skills, p_rules = self._patch_all()
        with p_mcp as m_mcp, p_skills as m_skills, p_rules as m_rules:
            assert run_setup(skills_only=True) == 0
            m_mcp.assert_not_called()
            m_skills.assert_called_once()
            m_rules.assert_called_once()

    def test_partial_mcp_fail(self):
        """V-014 / V-058: MCP fails but Skills+Rules succeed → exit 1."""
        p_mcp, p_skills, p_rules = self._patch_all(mcp=False)
        with p_mcp, p_skills, p_rules:
            assert run_setup() == 1

    def test_partial_skills_fail(self):
        """V-059: MCP+Rules ok, Skills fails → exit 1."""
        p_mcp, p_skills, p_rules = self._patch_all(skills=False)
        with p_mcp, p_skills, p_rules:
            assert run_setup() == 1

    def test_partial_rules_fail(self):
        """V-048: MCP+Skills ok, Rules fails → exit 1."""
        p_mcp, p_skills, p_rules = self._patch_all(rules=False)
        with p_mcp, p_skills, p_rules:
            assert run_setup() == 1

    def test_full_failure(self):
        """V-060: all three fail → exit 1."""
        p_mcp, p_skills, p_rules = self._patch_all(mcp=False, skills=False, rules=False)
        with p_mcp, p_skills, p_rules:
            assert run_setup() == 1

    def test_dry_run_no_ready_message(self, capsys: pytest.CaptureFixture[str]):
        p_mcp, p_skills, p_rules = self._patch_all()
        with p_mcp, p_skills, p_rules:
            assert run_setup(dry_run=True) == 0
        assert "Ready" not in capsys.readouterr().out

    def test_mutual_exclusion(self, capsys: pytest.CaptureFixture[str]):
        code = run_setup(mcp_only=True, skills_only=True)
        assert code == 1
        assert "mutually exclusive" in capsys.readouterr().err


# --- CLI integration ---


class TestCliIntegration:
    def test_setup_help(self):
        r = subprocess.run(
            [*BIN, "setup", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert r.returncode == 0
        assert "--mcp-only" in r.stdout
        assert "--skills-only" in r.stdout
        assert "--scope" in r.stdout
        assert "--dry-run" in r.stdout

    def test_setup_dry_run_skills_only(self):
        """Smoke test: --skills-only --dry-run runs without errors."""
        r = subprocess.run(
            [*BIN, "setup", "--skills-only", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert r.returncode == 0
        assert "Would link" in r.stdout

    def test_setup_mutual_exclusion_cli(self):
        """--mcp-only and --skills-only together errors at CLI level."""
        r = subprocess.run(
            [*BIN, "setup", "--mcp-only", "--skills-only", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert r.returncode != 0
        assert "mutually exclusive" in r.stderr
