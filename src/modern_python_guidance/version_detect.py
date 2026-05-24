"""Detect the target Python version for a project.

Precedence chain:
  1. CLI --python-version flag (explicit override)
  2. pyproject.toml [project].requires-python (PEP 621)
  3. .python-version file (pyenv/asdf)
  4. Default: 3.11
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

_KNOWN_MINORS = [
    Version(f"3.{minor}") for minor in range(7, 20)
]

_POETRY_CARET_RE = re.compile(r"\^(\d+\.\d+)")


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

    poetry_python = (
        data.get("tool", {}).get("poetry", {}).get("dependencies", {}).get("python")
    )
    if poetry_python:
        m = _POETRY_CARET_RE.search(str(poetry_python))
        if m:
            log.warning(
                "Poetry caret version '%s' is not PEP 440 — cannot parse precisely. "
                "Use --python-version or add [project].requires-python to pyproject.toml.",
                poetry_python,
            )
        else:
            log.warning(
                "Poetry python constraint '%s' detected but not supported. "
                "Use --python-version or add [project].requires-python.",
                poetry_python,
            )
        return None

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
