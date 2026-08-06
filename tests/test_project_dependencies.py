from __future__ import annotations

from pathlib import Path

import pytest

from modern_python_guidance.dependency_compat import assess_dependencies
from modern_python_guidance.project_dependencies import (
    _MAX_FILE_SIZE,
    _append_lock_facts,
    _append_overrides,
    _append_poetry_dependency,
    _append_requirement_list,
    _parse_override_key,
    _poetry_specifier,
    _read_toml,
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
version = "0.100.6"
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


def test_lock_only_transitive_package_is_non_confirming(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """[project.optional-dependencies]
api = ["fastapi>=0.95"]
"""
    )
    (tmp_path / "uv.lock").write_text(
        """[[package]]
name = "fastapi"
version = "0.112.0"

[[package]]
name = "starlette"
version = "0.37.2"
"""
    )

    context = detect_dependency_context(tmp_path)

    assert _status(context, "fastapi>=0.95") == "unknown"
    assert _status(context, "starlette>=0.26") == "unknown"


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


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("pyproject.toml", '[project]\ndependencies = ["pydantic>=2"]\n'),
        ("uv.lock", '[[package]]\nname = "pydantic"\nversion = "2.10.0"\n'),
        ("poetry.lock", '[[package]]\nname = "pydantic"\nversion = "2.10.0"\n'),
    ],
)
def test_external_evidence_symlink_is_not_read_or_selected(
    tmp_path: Path, filename: str, content: str
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    external = tmp_path / f"external-{filename}"
    external.write_text(content)
    (project / filename).symlink_to(external)

    detected = detect_dependency_context(project)
    assert detected.facts == {}
    assert any("outside project root" in warning for warning in detected.warnings)

    nested = project / "src"
    nested.mkdir()
    found = find_dependency_context(nested)
    assert found.facts == {}


def test_unreadable_or_missing_project_returns_only_valid_overrides(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    context = detect_dependency_context(missing, overrides={"pydantic": "2.7", "uv": None})

    assert _status(context, "pydantic>=2") == "confirmed"
    assert any("not readable" in warning for warning in context.warnings)
    assert any("invalid dependency override" in warning for warning in context.warnings)
    assert find_dependency_context(missing, overrides={"pydantic": "2.7"}).facts


def test_override_key_and_dependency_input_validation_is_conservative() -> None:
    assert _parse_override_key(("tool", "ruff")) == ("tool", "ruff")
    assert _parse_override_key(("invalid", "ruff")) is None
    assert _parse_override_key(("tool", "")) is None
    assert _parse_override_key(()) is None
    assert _parse_override_key(42) is None
    assert _parse_override_key("tool:") is None
    assert _parse_override_key("package:pydantic") == ("package", "pydantic")
    assert _parse_override_key("pydantic") == ("package", "pydantic")

    facts = []
    warnings: list[str] = []
    _append_overrides(facts, warnings, {"tool:": "1", "pydantic": "", 3: "2"})
    _append_requirement_list("pydantic>=2", "project.dependencies", facts, warnings)
    _append_requirement_list([3, "not a requirement @@@"], "project.dependencies", facts, warnings)

    assert not facts
    assert any("invalid dependency override" in warning for warning in warnings)
    assert any("non-list dependency field" in warning for warning in warnings)
    assert any("non-string dependency" in warning for warning in warnings)
    assert any("invalid dependency" in warning for warning in warnings)


def test_poetry_and_lock_schema_errors_are_warnings_not_evidence() -> None:
    facts = []
    warnings: list[str] = []
    _append_poetry_dependency("pydantic", {}, facts, warnings)
    _append_poetry_dependency("pydantic", "^invalid", facts, warnings)
    _append_poetry_dependency("pydantic", "~2", facts, warnings)
    _append_lock_facts({"package": "not a list"}, "uv.lock", facts, warnings)
    _append_lock_facts(
        {"package": ["not a table", {"name": "pydantic"}]}, "uv.lock", facts, warnings
    )

    assert facts == []
    assert any("non-list package entries" in warning for warning in warnings)
    assert any("malformed package entry" in warning for warning in warnings)
    assert any("unsupported Poetry dependency" in warning for warning in warnings)
    assert any("unsupported Poetry constraint" in warning for warning in warnings)
    assert any("without exact name/version" in warning for warning in warnings)
    assert _poetry_specifier("") is None
    assert _poetry_specifier("*") is None
    assert _poetry_specifier("^0.2.3") == ">=0.2.3,<0.3"
    assert _poetry_specifier("~2.4") == ">=2.4,<2.5"
    assert _poetry_specifier("=>2") is None


def test_read_toml_handles_invalid_utf8_and_os_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid_utf8 = tmp_path / "invalid.toml"
    invalid_utf8.write_bytes(b"\xff")
    warnings: list[str] = []

    assert _read_toml(invalid_utf8, warnings) is None
    assert "UnicodeDecodeError" in warnings[-1]

    readable = tmp_path / "readable.toml"
    readable.write_text("[project]\n")

    def fail_open(*_args: object, **_kwargs: object) -> None:
        raise OSError

    monkeypatch.setattr(Path, "open", fail_open)
    assert _read_toml(readable, warnings) is None
    assert "OSError" in warnings[-1]


def test_poetry_constraint_edge_cases_do_not_crash_or_claim_support() -> None:
    assert _poetry_specifier("^") is None
    assert _poetry_specifier("~1") is None
    assert _poetry_specifier("~=2.0") == "~=2.0"
