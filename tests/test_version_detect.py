from __future__ import annotations

import logging
from pathlib import Path

import pytest

from modern_python_guidance.version_detect import DEFAULT_VERSION, detect_version


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
            '[tool.poetry.dependencies.python]\noptional = true\n'
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
        (tmp_project / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\npython = "*"\n'
        )
        assert detect_version(project_dir=tmp_project) == DEFAULT_VERSION
        assert "not supported" in caplog.text

    def test_poetry_major_only_warns(self, tmp_project: Path, caplog):
        (tmp_project / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\npython = "^3"\n'
        )
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
        (tmp_project / "pyproject.toml").write_text(
            '[tool.poetry.dependencies]\npython = "*"\n'
        )
        (tmp_project / ".python-version").write_text("3.12\n")
        assert detect_version(project_dir=tmp_project) == "3.12"


class TestDefault:
    def test_empty_dir(self, tmp_project: Path):
        assert detect_version(project_dir=tmp_project) == DEFAULT_VERSION
