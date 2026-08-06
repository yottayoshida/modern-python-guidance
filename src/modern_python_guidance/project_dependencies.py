"""Read bounded dependency evidence from a project without executing it."""

from __future__ import annotations

import tomllib
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement

from modern_python_guidance.dependency_compat import DependencyContext, DependencyFact

_MAX_FILE_SIZE = 1024 * 1024
_MAX_WALK_DEPTH = 40
_EVIDENCE_FILES = ("pyproject.toml", "uv.lock", "poetry.lock")


def detect_dependency_context(
    project_dir: Path, overrides: Mapping[object, object] | None = None
) -> DependencyContext:
    """Collect bounded, read-only dependency observations from *project_dir*.

    Only files immediately in the supplied directory are read.  TOML parsing
    uses a 1 MiB cap and all malformed or unsupported input becomes a warning,
    never an exception or a command execution.
    """
    root = _as_directory(project_dir)
    facts: list[DependencyFact] = []
    warnings: list[str] = []
    _append_overrides(facts, warnings, overrides)
    if root is None:
        warnings.append(f"Project directory is not readable: {project_dir}")
        return _context(facts, warnings)

    pyproject = _read_toml(root / "pyproject.toml", warnings)
    if pyproject is not None:
        _append_pyproject_facts(pyproject, facts, warnings)
    for filename in ("uv.lock", "poetry.lock"):
        lock = _read_toml(root / filename, warnings)
        if lock is not None:
            _append_lock_facts(lock, filename, facts, warnings)
    _warn_ambiguous_locks(facts, warnings)
    return _context(facts, warnings)


def find_dependency_context(
    start_dir: Path, overrides: Mapping[object, object] | None = None
) -> DependencyContext:
    """Find the nearest project evidence without crossing a ``.git`` boundary."""
    current = _as_directory(start_dir)
    if current is None:
        return detect_dependency_context(start_dir, overrides)
    override_context = _context_from_overrides(overrides)
    for depth, directory in enumerate((current, *current.parents)):
        if depth > _MAX_WALK_DEPTH:
            break
        if any((directory / filename).is_file() for filename in _EVIDENCE_FILES):
            context = detect_dependency_context(directory, overrides)
            return context
        if (directory / ".git").exists():
            break
    return override_context


def _as_directory(path: Path) -> Path | None:
    try:
        resolved = path.resolve()
    except OSError:
        return None
    if resolved.is_file():
        return resolved.parent
    return resolved if resolved.is_dir() else None


def _read_toml(path: Path, warnings: list[str]) -> dict[object, object] | None:
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as file:
            text = file.read(_MAX_FILE_SIZE + 1)
    except (OSError, UnicodeDecodeError) as error:
        warnings.append(f"Could not read {path.name}: {type(error).__name__}")
        return None
    if len(text) > _MAX_FILE_SIZE:
        warnings.append(f"Dependency file too large, skipped: {path.name}")
        return None
    try:
        parsed = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, RecursionError) as error:
        warnings.append(f"Could not parse {path.name}: {type(error).__name__}")
        return None
    return parsed


def _append_overrides(
    facts: list[DependencyFact], warnings: list[str], overrides: Mapping[object, object] | None
) -> None:
    if overrides is None:
        return
    for raw_key, raw_version in overrides.items():
        parsed = _parse_override_key(raw_key)
        if parsed is None or not isinstance(raw_version, str) or not raw_version:
            warnings.append(f"Ignored invalid dependency override: {raw_key!r}")
            continue
        kind, name = parsed
        facts.append(DependencyFact(kind, name, raw_version, None, "override"))


def _context_from_overrides(overrides: Mapping[object, object] | None) -> DependencyContext:
    facts: list[DependencyFact] = []
    warnings: list[str] = []
    _append_overrides(facts, warnings, overrides)
    return _context(facts, warnings)


def _parse_override_key(raw_key: object) -> tuple[str, str] | None:
    if isinstance(raw_key, tuple) and len(raw_key) == 2:
        kind, name = raw_key
        if kind in {"package", "tool"} and isinstance(name, str) and name:
            return kind, name
        return None
    if not isinstance(raw_key, str) or not raw_key:
        return None
    if ":" in raw_key:
        kind, name = raw_key.split(":", 1)
        if kind in {"package", "tool"} and name:
            return kind, name
        return None
    return "package", raw_key


def _append_pyproject_facts(
    data: dict[object, object], facts: list[DependencyFact], warnings: list[str]
) -> None:
    project = data.get("project")
    if isinstance(project, dict):
        _append_requirement_list(
            project.get("dependencies"), "project.dependencies", facts, warnings
        )
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for requirements in optional.values():
                _append_requirement_list(
                    requirements, "project.optional-dependencies", facts, warnings
                )
    groups = data.get("dependency-groups")
    if isinstance(groups, dict):
        for requirements in groups.values():
            _append_requirement_list(requirements, "dependency-groups", facts, warnings)

    tool = data.get("tool")
    if isinstance(tool, dict):
        poetry = tool.get("poetry")
        if isinstance(poetry, dict):
            dependencies = poetry.get("dependencies")
            if isinstance(dependencies, dict):
                for name, value in dependencies.items():
                    if name == "python" or not isinstance(name, str):
                        continue
                    _append_poetry_dependency(name, value, facts, warnings)
        if "uv" in tool:
            facts.append(DependencyFact("tool", "uv", None, None, "tool-table"))
        if "ruff" in tool:
            facts.append(DependencyFact("tool", "ruff", None, None, "tool-table"))

    build_system = data.get("build-system")
    if isinstance(build_system, dict):
        _append_requirement_list(
            build_system.get("requires"), "build-system.requires", facts, warnings, kind="tool"
        )


def _append_requirement_list(
    raw_requirements: object,
    source: str,
    facts: list[DependencyFact],
    warnings: list[str],
    *,
    kind: str = "package",
) -> None:
    if raw_requirements is None:
        return
    if not isinstance(raw_requirements, list):
        warnings.append(f"Ignored non-list dependency field from {source}")
        return
    for raw in raw_requirements:
        if not isinstance(raw, str):
            warnings.append(f"Ignored non-string dependency from {source}")
            continue
        try:
            requirement = Requirement(raw)
        except InvalidRequirement:
            warnings.append(f"Ignored invalid dependency {raw!r} from {source}")
            continue
        fact_source = source if requirement.marker is None else f"{source}.marker"
        facts.append(
            DependencyFact(
                kind, requirement.name, None, str(requirement.specifier) or None, fact_source
            )
        )


def _append_poetry_dependency(
    name: str,
    raw_value: object,
    facts: list[DependencyFact],
    warnings: list[str],
) -> None:
    value = raw_value.get("version") if isinstance(raw_value, dict) else raw_value
    if not isinstance(value, str):
        warnings.append(f"Ignored unsupported Poetry dependency for {name}")
        return
    specifier = _poetry_specifier(value)
    if specifier is None and value not in {"", "*"}:
        warnings.append(f"Ignored unsupported Poetry constraint {value!r} for {name}")
        return
    facts.append(DependencyFact("package", name, None, specifier, "poetry.dependencies"))


def _poetry_specifier(value: str) -> str | None:
    if value in {"", "*"}:
        return None
    if value.startswith("^"):
        try:
            parts = [int(part) for part in value[1:].split(".")]
        except ValueError:
            return None
        if not parts:
            return None
        index = next((i for i, part in enumerate(parts) if part != 0), len(parts) - 1)
        upper = parts[: index + 1]
        upper[-1] += 1
        return f">={value[1:]},<{'.'.join(map(str, upper))}"
    if value.startswith("~") and not value.startswith("~="):
        try:
            parts = [int(part) for part in value[1:].split(".")]
        except ValueError:
            return None
        if len(parts) < 2:
            return None
        upper = parts[:2]
        upper[-1] += 1
        return f">={value[1:]},<{'.'.join(map(str, upper))}"
    try:
        Requirement(f"dependency{value}")
    except InvalidRequirement:
        return None
    return value


def _append_lock_facts(
    data: dict[object, object], source: str, facts: list[DependencyFact], warnings: list[str]
) -> None:
    packages = data.get("package")
    if packages is None:
        return
    if not isinstance(packages, list):
        warnings.append(f"Ignored non-list package entries from {source}")
        return
    for package in packages:
        if not isinstance(package, dict):
            warnings.append(f"Ignored malformed package entry from {source}")
            continue
        name = package.get("name")
        version = package.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            warnings.append(f"Ignored package without exact name/version from {source}")
            continue
        facts.append(DependencyFact("package", name, version, None, source))


def _warn_ambiguous_locks(facts: list[DependencyFact], warnings: list[str]) -> None:
    versions: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for fact in facts:
        if fact.source in {"uv.lock", "poetry.lock"} and fact.version is not None:
            versions[(fact.kind, fact.name, fact.source)].add(fact.version)
    for (_, name, source), known_versions in versions.items():
        if len(known_versions) > 1:
            warnings.append(
                f"{source} has multiple exact versions for {name}; applicability is unknown"
            )


def _context(facts: list[DependencyFact], warnings: list[str]) -> DependencyContext:
    grouped: dict[tuple[str, str], list[DependencyFact]] = defaultdict(list)
    for fact in facts:
        grouped[(fact.kind, fact.name)].append(fact)
    frozen_facts = {key: tuple(value) for key, value in grouped.items()}
    return DependencyContext(frozen_facts, tuple(warnings))
