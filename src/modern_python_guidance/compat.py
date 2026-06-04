"""Shared helpers used by search, retrieve, and CLI."""

from __future__ import annotations

import re

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

VERSION_RE = re.compile(r"^\d+\.\d+$")


def version_compatible(guide_python: str, target: str) -> bool:
    try:
        spec = SpecifierSet(guide_python)
        return Version(f"{target}.0") in spec
    except (InvalidSpecifier, InvalidVersion):
        return True


def token_estimate(body: str) -> int:
    return len(body) // 4
