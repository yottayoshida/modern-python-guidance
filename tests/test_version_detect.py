from __future__ import annotations

import logging
from pathlib import Path

import pytest

from modern_python_guidance.version_detect import (
    _MAX_CONFIG_SIZE,
    DEFAULT_VERSION,
    detect_configured_version,
    detect_version,
    find_configured_version,
)


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    return tmp_path


class TestCLIOverride:
    def test_cli_version_takes_priority(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.10"\n')
        assert detect_version(cli_version="3.12", project_dir=tmp_project) == "3.12"

    def test_cli_version_with_patch(self):
        assert detect_version(cli_version="3.12.3") == "3.12"


class TestPyprojectToml:
    def test_requires_python_gte(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.10"\n')
        assert detect_version(project_dir=tmp_project) == "3.10"

    def test_requires_python_range(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text(
            '[project]\nrequires-python = ">=3.10,<3.14"\n'
        )
        assert detect_version(project_dir=tmp_project) == "3.10"

    def test_requires_python_compatible(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text('[project]\nrequires-python = "~=3.11"\n')
        assert detect_version(project_dir=tmp_project) == "3.11"

    def test_requires_python_exact(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text('[project]\nrequires-python = "==3.12.*"\n')
        assert detect_version(project_dir=tmp_project) == "3.12"

    def test_requires_python_patch_level(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11.4"\n')
        assert detect_version(project_dir=tmp_project) == "3.11"

    def test_poetry_caret(self, tmp_project: Path, caplog):
        (tmp_project / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\npython = "^3.10"\n'
        )
        with caplog.at_level(logging.INFO):
            assert detect_version(project_dir=tmp_project) == "3.10"
        assert "Parsed Poetry caret" in caplog.text

    def test_poetry_caret_with_patch(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\npython = "^3.10.2"\n'
        )
        assert detect_version(project_dir=tmp_project) == "3.10"

    def test_poetry_tilde(self, tmp_project: Path, caplog):
        (tmp_project / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\npython = "~3.11"\n'
        )
        with caplog.at_level(logging.INFO):
            assert detect_version(project_dir=tmp_project) == "3.11"
        assert "Parsed Poetry tilde" in caplog.text

    def test_poetry_tilde_with_patch(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\npython = "~3.11.5"\n'
        )
        assert detect_version(project_dir=tmp_project) == "3.11"

    def test_poetry_pep440_range(self, tmp_project: Path, caplog):
        (tmp_project / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\npython = ">=3.10,<3.14"\n'
        )
        with caplog.at_level(logging.INFO):
            assert detect_version(project_dir=tmp_project) == "3.10"
        assert "Parsed Poetry PEP 440" in caplog.text

    def test_poetry_pep440_compatible(self, tmp_project: Path, caplog):
        (tmp_project / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\npython = "~=3.11"\n'
        )
        with caplog.at_level(logging.INFO):
            assert detect_version(project_dir=tmp_project) == "3.11"
        assert "Parsed Poetry PEP 440" in caplog.text
        assert "Parsed Poetry tilde" not in caplog.text

    def test_poetry_dict_form(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text(
            '[tool.poetry.dependencies.python]\nversion = "^3.10"\n'
        )
        assert detect_version(project_dir=tmp_project) == "3.10"

    def test_poetry_dict_no_version_key(self, tmp_project: Path, caplog):
        (tmp_project / "pyproject.toml").write_text(
            "[tool.poetry.dependencies.python]\noptional = true\n"
        )
        assert detect_version(project_dir=tmp_project) == DEFAULT_VERSION
        assert "no 'version' key" in caplog.text

    def test_poetry_union_warns(self, tmp_project: Path, caplog):
        (tmp_project / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\npython = "^3.10 || ^3.12"\n'
        )
        assert detect_version(project_dir=tmp_project) == DEFAULT_VERSION
        assert "union constraint" in caplog.text

    def test_poetry_unsupported_warns(self, tmp_project: Path, caplog):
        (tmp_project / "pyproject.toml").write_text('[tool.poetry.dependencies]\npython = "*"\n')
        assert detect_version(project_dir=tmp_project) == DEFAULT_VERSION
        assert "not supported" in caplog.text

    def test_poetry_major_only_warns(self, tmp_project: Path, caplog):
        (tmp_project / "pyproject.toml").write_text('[tool.poetry.dependencies]\npython = "^3"\n')
        assert detect_version(project_dir=tmp_project) == DEFAULT_VERSION
        assert "not supported" in caplog.text

    def test_poetry_list_type_warns(self, tmp_project: Path, caplog):
        (tmp_project / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\npython = ["^3.10", "^3.12"]\n'
        )
        assert detect_version(project_dir=tmp_project) == DEFAULT_VERSION
        assert "unexpected type" in caplog.text

    def test_malformed_toml(self, tmp_project: Path, caplog):
        (tmp_project / "pyproject.toml").write_text("this is not valid toml [[[")
        result = detect_version(project_dir=tmp_project)
        assert result == DEFAULT_VERSION
        assert "Failed to parse" in caplog.text

    def test_empty_pyproject(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text("")
        assert detect_version(project_dir=tmp_project) == DEFAULT_VERSION


class TestPythonVersionFile:
    def test_simple_version(self, tmp_project: Path):
        (tmp_project / ".python-version").write_text("3.12\n")
        assert detect_version(project_dir=tmp_project) == "3.12"

    def test_patch_version(self, tmp_project: Path):
        (tmp_project / ".python-version").write_text("3.12.3\n")
        assert detect_version(project_dir=tmp_project) == "3.12"

    def test_system_skipped(self, tmp_project: Path):
        (tmp_project / ".python-version").write_text("system\n")
        assert detect_version(project_dir=tmp_project) == DEFAULT_VERSION

    def test_pypy_skipped(self, tmp_project: Path):
        (tmp_project / ".python-version").write_text("pypy3.10-7.3.12\n")
        assert detect_version(project_dir=tmp_project) == DEFAULT_VERSION

    def test_trailing_whitespace(self, tmp_project: Path):
        (tmp_project / ".python-version").write_text("  3.11  \n")
        assert detect_version(project_dir=tmp_project) == "3.11"


class TestPrecedence:
    def test_pyproject_over_python_version_file(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12"\n')
        (tmp_project / ".python-version").write_text("3.10\n")
        assert detect_version(project_dir=tmp_project) == "3.12"

    def test_poetry_wins_over_python_version_file(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\npython = "^3.10"\n'
        )
        (tmp_project / ".python-version").write_text("3.11\n")
        assert detect_version(project_dir=tmp_project) == "3.10"

    def test_poetry_unsupported_falls_to_python_version_file(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text('[tool.poetry.dependencies]\npython = "*"\n')
        (tmp_project / ".python-version").write_text("3.12\n")
        assert detect_version(project_dir=tmp_project) == "3.12"


class TestDefault:
    def test_empty_dir(self, tmp_project: Path):
        assert detect_version(project_dir=tmp_project) == DEFAULT_VERSION


class TestDetectConfiguredVersion:
    """detect_configured_version never falls back to DEFAULT_VERSION."""

    def test_pyproject_detected(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.8"\n')
        assert detect_configured_version(tmp_project) == "3.8"

    def test_python_version_file_detected(self, tmp_project: Path):
        (tmp_project / ".python-version").write_text("3.9\n")
        assert detect_configured_version(tmp_project) == "3.9"

    def test_empty_dir_returns_none(self, tmp_project: Path):
        assert detect_configured_version(tmp_project) is None

    def test_pyproject_without_version_returns_none(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text('[tool.other]\nkey = "v"\n')
        assert detect_configured_version(tmp_project) is None

    def test_malformed_pyproject_returns_none(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text("not [valid toml")
        assert detect_configured_version(tmp_project) is None

    def test_malformed_pyproject_falls_to_python_version_file(self, tmp_project: Path):
        (tmp_project / "pyproject.toml").write_text("not [valid toml")
        (tmp_project / ".python-version").write_text("3.9\n")
        assert detect_configured_version(tmp_project) == "3.9"


class TestConfigSizeLimit:
    def test_size_cap_is_one_mib(self):
        """The 1 MiB cap is a documented spec value (CHANGELOG), not a free variable."""
        assert _MAX_CONFIG_SIZE == 1024 * 1024

    def test_oversized_pyproject_skipped(self, tmp_project: Path, caplog):
        pyproject = tmp_project / "pyproject.toml"
        padding = "# " + "x" * _MAX_CONFIG_SIZE + "\n"
        pyproject.write_text(f'[project]\nrequires-python = ">=3.8"\n{padding}')
        with caplog.at_level(logging.WARNING):
            assert detect_configured_version(tmp_project) is None
        assert "too large" in caplog.text

    def test_oversized_python_version_file_skipped(self, tmp_project: Path):
        pv = tmp_project / ".python-version"
        pv.write_text("3.9" + " " * _MAX_CONFIG_SIZE + "\n")
        assert detect_configured_version(tmp_project) is None

    def test_python_version_file_at_limit_still_read(self, tmp_project: Path):
        content = "3.9"
        padding = " " * (_MAX_CONFIG_SIZE - len(content))
        (tmp_project / ".python-version").write_text(content + padding)
        assert detect_configured_version(tmp_project) == "3.9"

    def test_at_limit_still_read(self, tmp_project: Path):
        content = '[project]\nrequires-python = ">=3.8"\n'
        padding = "# " + "x" * (_MAX_CONFIG_SIZE - len(content) - 3) + "\n"
        (tmp_project / "pyproject.toml").write_text(content + padding)
        assert detect_configured_version(tmp_project) == "3.8"


class TestFindConfiguredVersionBoundary:
    """V-001..V-007: .git boundary stops the upward walk."""

    def test_git_dir_with_config_returns_version(self, tmp_path: Path):
        """V-001: .git + pyproject.toml in same dir — config is found."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        (repo / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.10"\n')
        sub = repo / "pkg" / "src"
        sub.mkdir(parents=True)
        assert find_configured_version(sub) == "3.10"

    def test_git_file_recognized_as_boundary(self, tmp_path: Path):
        """V-002: .git as file (worktree/submodule) stops the walk."""
        parent = tmp_path / "parent"
        parent.mkdir()
        (parent / ".python-version").write_text("3.8\n")
        worktree = parent / "wt"
        worktree.mkdir()
        (worktree / ".git").write_text("gitdir: /some/fake/path\n")
        sub = worktree / "src"
        sub.mkdir()
        assert find_configured_version(sub) is None

    def test_boundary_blocks_parent_config(self, tmp_path: Path):
        """V-003: .git boundary prevents leaking to parent's .python-version."""
        (tmp_path / ".python-version").write_text("3.8\n")
        repo = tmp_path / "project"
        repo.mkdir()
        (repo / ".git").mkdir()
        sub = repo / "src"
        sub.mkdir()
        assert find_configured_version(sub) is None

    def test_no_git_walks_to_depth_limit(self, tmp_path: Path):
        """V-004: without .git, walk continues (existing depth behavior)."""
        (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.9"\n')
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        assert find_configured_version(deep) == "3.9"

    def test_nested_repo_inner_boundary_stops(self, tmp_path: Path):
        """V-005: inner .git stops walk, outer repo config not reached."""
        outer = tmp_path / "outer"
        outer.mkdir()
        (outer / ".git").mkdir()
        (outer / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.8"\n')
        inner = outer / "vendor" / "inner"
        inner.mkdir(parents=True)
        (inner / ".git").mkdir()
        sub = inner / "src"
        sub.mkdir()
        assert find_configured_version(sub) is None

    def test_monorepo_child_config_wins(self, tmp_path: Path):
        """V-006: child config found before reaching .git root."""
        repo = tmp_path / "mono"
        repo.mkdir()
        (repo / ".git").mkdir()
        (repo / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.8"\n')
        svc = repo / "services" / "api"
        svc.mkdir(parents=True)
        (svc / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12"\n')
        src = svc / "src"
        src.mkdir()
        assert find_configured_version(src) == "3.12"

    def test_monorepo_child_no_version_falls_to_root(self, tmp_path: Path):
        """V-007: child pyproject without version skipped, root config used."""
        repo = tmp_path / "mono"
        repo.mkdir()
        (repo / ".git").mkdir()
        (repo / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.10"\n')
        svc = repo / "services" / "api"
        svc.mkdir(parents=True)
        (svc / "pyproject.toml").write_text("[tool.other]\nkey = 1\n")
        assert find_configured_version(svc) == "3.10"
