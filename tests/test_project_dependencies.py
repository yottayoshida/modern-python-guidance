from __future__ import annotations

from pathlib import Path

from modern_python_guidance.dependency_compat import assess_dependencies
from modern_python_guidance.project_dependencies import (
    _MAX_FILE_SIZE,
    detect_dependency_context,
    find_dependency_context,
)


def _status(context, requirement: str) -> str:
    return assess_dependencies(
        package_requirements=(requirement,), tool_requirements=(), context=context
    ).status


def test_detects_pep621_main_dependency_and_optional_groups_are_non_confirming(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """[project]
dependencies = ["pydantic>=2,<3"]

[project.optional-dependencies]
db = ["sqlalchemy>=2"]

[dependency-groups]
test = ["django>=5.1"]
"""
    )

    context = detect_dependency_context(tmp_path)

    assert _status(context, "pydantic>=2") == "confirmed"
    assert _status(context, "sqlalchemy>=2") == "unknown"
    assert _status(context, "django>=5.1") == "unknown"


def test_detects_poetry_main_dependencies_and_exact_lock_versions(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """[tool.poetry.dependencies]
python = ">=3.11"
fastapi = "^0.100"
"""
    )
    (tmp_path / "poetry.lock").write_text(
        """[[package]]
name = "fastapi"
version = "0.112.0"
"""
    )

    context = detect_dependency_context(tmp_path)

    assert _status(context, "fastapi>=0.95") == "confirmed"
    facts = context.facts[("package", "fastapi")]
    assert {fact.source for fact in facts} == {"poetry.dependencies", "poetry.lock"}


def test_poetry_conditional_table_dependencies_are_non_confirming(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """[tool.poetry.dependencies]
pydantic = { version = ">=2", optional = true }
fastapi = { version = ">=0.95", markers = "python_version >= '3.12'" }
django = { version = ">=5.1", python = ">=3.12" }
httpx = { version = ">=0.23", platform = "linux" }
"""
    )

    context = detect_dependency_context(tmp_path)

    assert _status(context, "pydantic>=2") == "unknown"
    assert _status(context, "fastapi>=0.95") == "unknown"
    assert _status(context, "django>=5.1") == "unknown"
    assert _status(context, "httpx>=0.23") == "unknown"


def test_lock_for_optional_or_conditional_dependency_is_non_confirming(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """[project]
dependencies = ["fastapi>=0.95"]

[project.optional-dependencies]
extra = ["pydantic>=2"]

[tool.poetry.dependencies]
django = { version = ">=5.1", optional = true }
"""
    )
    (tmp_path / "uv.lock").write_text(
        """[[package]]
name = "pydantic"
version = "2.7.4"

[[package]]
name = "fastapi"
version = "0.112.0"
"""
    )
    (tmp_path / "poetry.lock").write_text(
        """[[package]]
name = "django"
version = "5.1.0"
"""
    )

    context = detect_dependency_context(tmp_path)

    assert _status(context, "pydantic>=2") == "unknown"
    assert _status(context, "django>=5.1") == "unknown"
    assert _status(context, "fastapi>=0.95") == "confirmed"


def test_optional_lock_package_is_non_confirming_without_main_declaration(tmp_path: Path) -> None:
    (tmp_path / "poetry.lock").write_text(
        """[[package]]
name = "pydantic"
version = "2.7.4"
optional = true
"""
    )

    context = detect_dependency_context(tmp_path)

    assert _status(context, "pydantic>=2") == "unknown"


def test_multiple_lock_versions_are_ambiguous(tmp_path: Path) -> None:
    (tmp_path / "uv.lock").write_text(
        """[[package]]
name = "pydantic"
version = "1.10.15"

[[package]]
name = "pydantic"
version = "2.7.4"
"""
    )

    context = detect_dependency_context(tmp_path)

    assert _status(context, "pydantic>=2") == "unknown"
    assert any("multiple exact versions" in warning for warning in context.warnings)


def test_explicit_overrides_win_and_normalize_names(tmp_path: Path) -> None:
    (tmp_path / "uv.lock").write_text(
        """[[package]]
name = "pydantic"
version = "1.10.15"
"""
    )

    context = detect_dependency_context(
        tmp_path,
        overrides={"package:PyDantic": "2.7.4", "tool:uv": "0.4.0"},
    )

    assert _status(context, "pydantic>=2") == "confirmed"
    assert (
        assess_dependencies(
            package_requirements=(), tool_requirements=("uv",), context=context
        ).status
        == "confirmed"
    )


def test_detects_tool_evidence_without_treating_tool_table_presence_as_installed(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """[build-system]
requires = ["pip>=21.3"]

[tool.uv]

[tool.ruff]
line-length = 99
"""
    )

    context = detect_dependency_context(tmp_path)

    assert (
        assess_dependencies(
            package_requirements=(), tool_requirements=("pip>=21.3",), context=context
        ).status
        == "confirmed"
    )
    assert (
        assess_dependencies(
            package_requirements=(), tool_requirements=("uv",), context=context
        ).status
        == "unknown"
    )
    assert (
        assess_dependencies(
            package_requirements=(), tool_requirements=("ruff",), context=context
        ).status
        == "unknown"
    )


def test_find_stops_at_git_boundary_and_uses_nearest_evidence(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "pyproject.toml").write_text('[project]\ndependencies = ["pydantic>=2"]\n')
    repo = parent / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    nested = repo / "src" / "nested"
    nested.mkdir(parents=True)

    assert _status(find_dependency_context(nested), "pydantic>=2") == "unknown"

    (repo / "pyproject.toml").write_text('[project]\ndependencies = ["pydantic>=2"]\n')
    assert _status(find_dependency_context(nested), "pydantic>=2") == "confirmed"


def test_malformed_or_oversized_files_are_skipped_without_raising(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("not valid TOML [[[")
    context = detect_dependency_context(tmp_path)
    assert context.facts == {}
    assert context.warnings

    oversized = tmp_path / "uv.lock"
    oversized.write_text("x" * (_MAX_FILE_SIZE + 1))
    context = detect_dependency_context(tmp_path)
    assert context.facts == {}
    assert any("too large" in warning for warning in context.warnings)


def test_size_limit_is_measured_in_bytes_before_utf8_decoding(tmp_path: Path) -> None:
    (tmp_path / "uv.lock").write_text("é" * (_MAX_FILE_SIZE // 2 + 1))

    context = detect_dependency_context(tmp_path)

    assert any("too large" in warning for warning in context.warnings)


def test_malformed_but_valid_toml_schema_is_ignored_without_raising(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('tool = "not a table"\n')

    context = detect_dependency_context(tmp_path)

    assert context.facts == {}


def test_starting_at_a_file_uses_its_parent_and_does_not_leave_boundary(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "pyproject.toml").write_text('[project]\ndependencies = ["httpx>=0.23"]\n')
    module = repo / "package" / "module.py"
    module.parent.mkdir()
    module.write_text("")

    assert _status(find_dependency_context(module), "httpx>=0.23") == "confirmed"
