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

    pyproject = project_dir / "pyproject.toml"
    if pyproject.is_file():
        result = _from_pyproject(pyproject)
        if result is not None:
            return result

    python_version_file = project_dir / ".python-version"
    if python_version_file.is_file():
        result = _from_python_version_file(python_version_file)
        if result is not None:
            return result

    log.info("No version config found, using default %s", DEFAULT_VERSION)
    return DEFAULT_VERSION


def _from_pyproject(path: Path) -> str | None:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        log.warning("Failed to parse %s: %s", path, e)
        return None

    requires_python = data.get("project", {}).get("requires-python")
    if requires_python:
        return _min_version_from_specifier(requires_python)

    poetry_python = data.get("tool", {}).get("poetry", {}).get("dependencies", {}).get("python")
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
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError as e:
        log.warning("Failed to read %s: %s", path, e)
        return None

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
