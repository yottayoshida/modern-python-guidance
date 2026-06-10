"""Detect the target Python version for a project.

Precedence chain:
  1. CLI --python-version flag (explicit override)
  2. pyproject.toml [project].requires-python (PEP 621)
  3. pyproject.toml [tool.poetry.dependencies].python (caret/tilde/PEP 440)
  4. .python-version file (pyenv/asdf)
  5. Default: 3.11
"""

from __future__ import annotations

import logging
import re
import tomllib
from pathlib import Path

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version

log = logging.getLogger(__name__)

DEFAULT_VERSION = "3.11"

# Config files are read by the PostToolUse hook on every edit; cap the size so a
# crafted pyproject.toml cannot stall or exhaust the hook process.
_MAX_CONFIG_SIZE = 1024 * 1024

# Upper bound for the upward search in find_configured_version: ancestors of a
# resolved path are finite, so this only caps pathological nesting depth.
_MAX_WALK_DEPTH = 40

_KNOWN_MINORS = [Version(f"3.{minor}") for minor in range(7, 20)]

_POETRY_CARET_RE = re.compile(r"\^(\d+\.\d+)")
_POETRY_TILDE_RE = re.compile(r"~(\d+\.\d+)")


def detect_version(
    *,
    cli_version: str | None = None,
    project_dir: Path | None = None,
) -> str:
    if cli_version is not None:
        return _normalize(cli_version)

    if project_dir is None:
        project_dir = Path.cwd()

    project_dir = project_dir.resolve()

    result = detect_configured_version(project_dir)
    if result is not None:
        return result

    log.info("No version config found, using default %s", DEFAULT_VERSION)
    return DEFAULT_VERSION


def find_configured_version(start_dir: Path) -> str | None:
    """Walk upward from *start_dir* to the nearest usable version config.

    A directory whose config exists but yields no version (e.g. a pyproject
    without requires-python) is skipped and the walk continues upward.
    Returns None when no ancestor has a usable config.
    """
    for current in (start_dir, *start_dir.parents)[: _MAX_WALK_DEPTH + 1]:
        version = detect_configured_version(current)
        if version is not None:
            return version
    return None


def detect_configured_version(project_dir: Path) -> str | None:
    """Return the version configured in *project_dir* itself, or None.

    Unlike detect_version(), this never falls back to DEFAULT_VERSION, so
    callers can distinguish "configured here" from "no usable config here".
    """
    pyproject = project_dir / "pyproject.toml"
    if pyproject.is_file():
        result = _from_pyproject(pyproject)
        if result is not None:
            return result

    python_version_file = project_dir / ".python-version"
    if python_version_file.is_file():
        return _from_python_version_file(python_version_file)

    return None


def _read_config_text(path: Path) -> str | None:
    # Bounded read (not stat-then-read): the cap holds even if the file grows
    # while the hook runs, and undecodable bytes must not raise — the hook
    # walks ancestor directories it does not control.
    try:
        with path.open(encoding="utf-8") as f:
            text = f.read(_MAX_CONFIG_SIZE + 1)
    except (OSError, UnicodeDecodeError) as e:
        log.warning("Failed to read %s: %s", path, e)
        return None
    if len(text) > _MAX_CONFIG_SIZE:
        log.warning("Config file too large, skipping: %s", path)
        return None
    return text


def _from_pyproject(path: Path) -> str | None:
    text = _read_config_text(path)
    if text is None:
        return None
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, RecursionError) as e:
        # RecursionError: deeply nested TOML (e.g. thousands of '[') blows the
        # stack well under the size cap.
        log.warning("Failed to parse %s: %s", path, type(e).__name__)
        return None

    # Valid TOML can still violate the pyproject schema (e.g. `project = "x"`),
    # so every level is type-checked before access.
    project = data.get("project")
    requires_python = project.get("requires-python") if isinstance(project, dict) else None
    if isinstance(requires_python, str) and requires_python:
        return _min_version_from_specifier(requires_python)
    if requires_python is not None and not isinstance(requires_python, str):
        # An empty string falls through silently (matching the old behavior);
        # only genuinely wrong types are worth a warning.
        log.warning(
            "requires-python has unexpected type %s in %s",
            type(requires_python).__name__,
            path,
        )

    tool = data.get("tool")
    poetry = tool.get("poetry") if isinstance(tool, dict) else None
    dependencies = poetry.get("dependencies") if isinstance(poetry, dict) else None
    poetry_python = dependencies.get("python") if isinstance(dependencies, dict) else None
    if poetry_python:
        result = _parse_poetry_python(poetry_python)
        if result is not None:
            return result

    return None


def _parse_poetry_python(value: str | dict) -> str | None:
    if isinstance(value, dict):
        value = value.get("version")
        if not value:
            log.warning("Poetry python constraint has no 'version' key")
            return None

    if not isinstance(value, str):
        log.warning("Poetry python constraint has unexpected type %s", type(value).__name__)
        return None

    poetry_str = value

    if "||" in poetry_str:
        log.warning(
            "Poetry union constraint '%s' is not supported. "
            "Use --python-version or add [project].requires-python.",
            poetry_str,
        )
        return None

    m = _POETRY_CARET_RE.search(poetry_str)
    if m:
        log.info("Parsed Poetry caret constraint '%s' → %s", poetry_str, m.group(1))
        return m.group(1)

    m = _POETRY_TILDE_RE.search(poetry_str)
    if m:
        log.info("Parsed Poetry tilde constraint '%s' → %s", poetry_str, m.group(1))
        return m.group(1)

    result = _min_version_from_specifier(poetry_str)
    if result is not None:
        log.info("Parsed Poetry PEP 440 constraint '%s' → %s", poetry_str, result)
        return result

    log.warning(
        "Poetry python constraint '%s' detected but not supported. "
        "Use --python-version or add [project].requires-python.",
        poetry_str,
    )
    return None


def _from_python_version_file(path: Path) -> str | None:
    text = _read_config_text(path)
    if text is None:
        return None

    content = text.strip()
    if not content or content == "system":
        return None

    if content.startswith("pypy") or content.startswith("graalpy"):
        log.info("Skipping non-CPython version: %s", content)
        return None

    match = re.match(r"(\d+\.\d+)", content)
    if match:
        return match.group(1)

    return None


def _min_version_from_specifier(spec_str: str) -> str | None:
    try:
        spec = SpecifierSet(spec_str)
    except InvalidSpecifier:
        log.warning("Invalid version specifier: %s", spec_str)
        return None

    for v in _KNOWN_MINORS:
        if v in spec:
            return f"{v.major}.{v.minor}"
        high_patch = Version(f"{v.major}.{v.minor}.99")
        if high_patch in spec:
            return f"{v.major}.{v.minor}"

    log.warning("No known Python version matches specifier: %s", spec_str)
    return None


def _normalize(version: str) -> str:
    match = re.match(r"(\d+\.\d+)", version)
    if match:
        return match.group(1)
    return version
