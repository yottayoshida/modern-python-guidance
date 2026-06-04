"""Scan a Python file for outdated patterns against guide definitions."""

from __future__ import annotations

import io
import re
import tokenize as _tokenize
from dataclasses import dataclass
from pathlib import Path

from modern_python_guidance.compat import version_compatible
from modern_python_guidance.guide_index import Guide, GuideIndex, _code_lines

FREQ_RANK = {"high": 0, "medium": 1, "low": 2}


class CheckError(Exception):
    """Raised for unrecoverable file-level errors (not found, binary, unreadable)."""


_MAX_LINE_LEN = 10_240
_BINARY_PROBE_SIZE = 8192
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass
class CheckMatch:
    line: int
    source_line: str
    guide_id: str
    guide_title: str
    category: str
    frequency: str
    snippet: str


def _string_lines(text: str) -> frozenset[int]:
    """Line numbers belonging to multi-line STRING tokens (docstrings etc.)."""
    skip: set[int] = set()
    try:
        tokens = _tokenize.generate_tokens(io.StringIO(text).readline)
        string_types = {_tokenize.STRING}
        fstring_mid = getattr(_tokenize, "FSTRING_MIDDLE", None)
        if fstring_mid is not None:
            string_types.add(fstring_mid)
        for tok in tokens:
            if tok.type in string_types and tok.end[0] > tok.start[0]:
                skip.update(range(tok.start[0], tok.end[0] + 1))
    except _tokenize.TokenError:
        return frozenset()
    return frozenset(skip)


def check_file(
    path: Path,
    index: GuideIndex,
    *,
    python_version: str | None = None,
) -> list[CheckMatch]:
    _validate_file(path)
    text = _read_file(path)
    if not text:
        return []

    patterns = _build_patterns(index, python_version=python_version)
    if not patterns:
        return []

    skip = _string_lines(text)
    matches: list[CheckMatch] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if lineno in skip:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if len(line) > _MAX_LINE_LEN:
            continue

        for compiled, guide in patterns:
            if compiled.search(line):
                matches.append(
                    CheckMatch(
                        line=lineno,
                        source_line=line,
                        guide_id=guide.meta.id,
                        guide_title=guide.meta.title,
                        category=guide.meta.category,
                        frequency=guide.meta.frequency,
                        snippet=guide.snippet,
                    )
                )
                break

    return matches


def _validate_file(path: Path) -> None:
    if not path.exists():
        raise CheckError(f"file not found: {path}")
    if not path.is_file():
        raise CheckError(f"not a file: {path}")


def _read_file(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise CheckError(f"cannot read {path}: {e}") from e

    probe = raw[:_BINARY_PROBE_SIZE]
    if b"\x00" in probe:
        raise CheckError(f"binary file: {path}")

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def _build_patterns(
    index: GuideIndex,
    *,
    python_version: str | None = None,
) -> list[tuple[re.Pattern[str], Guide]]:
    entries: list[tuple[re.Pattern[str], Guide]] = []

    for guide in index.guides.values():
        if python_version and not version_compatible(guide.meta.python, python_version):
            continue

        raw_patterns = _get_patterns(guide)
        for pat_str in raw_patterns:
            try:
                compiled = re.compile(pat_str)
                entries.append((compiled, guide))
            except re.error:
                pass

    entries.sort(key=lambda e: (e[1].meta.layer, FREQ_RANK.get(e[1].meta.frequency, 2)))
    return entries


def _get_patterns(guide: Guide) -> list[str]:
    if guide.meta.detect_patterns is not None:
        return guide.meta.detect_patterns
    return _auto_extract_patterns(guide)


def _auto_extract_patterns(guide: Guide) -> list[str]:
    bad_lines = _code_lines(guide.body, "## BAD")
    patterns: list[str] = []
    for line in bad_lines:
        stripped = line.strip()
        if stripped.startswith(("from ", "import ")):
            escaped = re.escape(stripped)
            patterns.append(escaped)
        elif stripped.startswith("@"):
            parts = stripped.split("(", 1)
            escaped = re.escape(parts[0])
            patterns.append(escaped)
    return patterns


def sanitize_line(text: str) -> str:
    text = _ANSI_RE.sub("", text)
    return _CTRL_RE.sub("", text)
