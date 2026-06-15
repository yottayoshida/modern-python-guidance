"""Scan a Python file for outdated patterns against guide definitions.

SECURITY: This module NEVER executes user code.
Only ast.parse(), ast.walk(), tokenize, and node attribute inspection are used.
compile(), exec(), eval(), importlib are FORBIDDEN on user file content.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize as _tokenize
from dataclasses import dataclass
from pathlib import Path

from modern_python_guidance.compat import version_compatible
from modern_python_guidance.guide_index import Guide, GuideIndex, _code_lines

FREQ_RANK = {"high": 0, "medium": 1, "low": 2}
_MAX_FILE_SIZE = 2 * 1024 * 1024


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


def _mask_strings(text: str) -> tuple[frozenset[int], dict[int, str]]:
    """Return (skip_lines, masked_lines) for string/comment-aware regex matching.

    skip_lines: line numbers wholly inside multi-line strings (skip entirely).
    masked_lines: {lineno: line_with_string/comment_spans_blanked} for single-line masking.
    """
    skip: set[int] = set()
    lines = text.splitlines()
    masked_chars: dict[int, list[tuple[int, int]]] = {}

    try:
        tokens = _tokenize.generate_tokens(io.StringIO(text).readline)
        string_types = {_tokenize.STRING}
        fstring_mid = getattr(_tokenize, "FSTRING_MIDDLE", None)
        if fstring_mid is not None:
            string_types.add(fstring_mid)

        for tok in tokens:
            if tok.type == _tokenize.COMMENT:
                masked_chars.setdefault(tok.start[0], []).append((tok.start[1], tok.end[1]))
            elif tok.type in string_types:
                if tok.end[0] > tok.start[0]:
                    for ln in range(tok.start[0] + 1, tok.end[0]):
                        skip.add(ln)
                    masked_chars.setdefault(tok.start[0], []).append(
                        (tok.start[1], len(lines[tok.start[0] - 1]))
                    )
                    masked_chars.setdefault(tok.end[0], []).append((0, tok.end[1]))
                else:
                    masked_chars.setdefault(tok.start[0], []).append((tok.start[1], tok.end[1]))
    except (_tokenize.TokenError, SyntaxError, IndentationError):
        return frozenset(), {}

    masked_lines: dict[int, str] = {}
    for lineno, spans in masked_chars.items():
        if lineno in skip or lineno < 1 or lineno > len(lines):
            continue
        chars = list(lines[lineno - 1])
        for start, end in spans:
            for i in range(start, min(end, len(chars))):
                chars[i] = " "
        masked_lines[lineno] = "".join(chars)

    return frozenset(skip), masked_lines


def check_file(
    path: Path,
    index: GuideIndex,
    *,
    python_version: str | None = None,
) -> list[CheckMatch]:
    _validate_file(path)
    file_size = path.stat().st_size
    if file_size > _MAX_FILE_SIZE:
        raise CheckError(f"file too large ({file_size} bytes, max {_MAX_FILE_SIZE}): {path}")
    text = _read_file(path)
    if not text:
        return []

    patterns = _build_patterns(index, python_version=python_version)
    name_guides = _build_name_guides(index, python_version=python_version)

    if not patterns and not name_guides:
        return []

    skip, masked = _mask_strings(text)

    # Regex-based detection
    regex_matches: list[CheckMatch] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if lineno in skip:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if len(line) > _MAX_LINE_LEN:
            continue

        match_line = masked.get(lineno, line)
        for compiled, guide in patterns:
            if compiled.search(match_line):
                regex_matches.append(
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

    # AST-based detection (detect-names)
    ast_matches: list[CheckMatch] = []
    if name_guides:
        result = _parse_imports(text)
        if result is not None:
            aliases, tree = result
            ast_matches = _ast_detect_names(text, tree, aliases, name_guides)

    # Merge: one match per line; AST preferred over regex on same line
    merged = _merge_matches(regex_matches, ast_matches)
    return merged


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


def _build_name_guides(
    index: GuideIndex,
    *,
    python_version: str | None = None,
) -> dict[str, Guide]:
    """Build {fqn: Guide} mapping from guides that have detect_names."""
    result: dict[str, Guide] = {}
    for guide in index.guides.values():
        if python_version and not version_compatible(guide.meta.python, python_version):
            continue
        if guide.meta.detect_names:
            for name in guide.meta.detect_names:
                result[name] = guide
    return result


def _parse_imports(text: str) -> tuple[dict[str, str], ast.Module] | None:
    """Parse imports and return (alias_map, AST tree), or None on SyntaxError."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None

    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                name = a.asname or a.name
                aliases[name] = a.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for a in node.names:
                fqn = f"{mod}.{a.name}" if mod else a.name
                name = a.asname or a.name
                aliases[name] = fqn
    return aliases, tree


def _resolve_fqn(node: ast.expr, aliases: dict[str, str]) -> str | None:
    """Resolve an AST node to its fully qualified name via the alias map."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id)
    if isinstance(node, ast.Attribute):
        parent = _resolve_fqn(node.value, aliases)
        if parent is not None:
            return f"{parent}.{node.attr}"
    return None


def _is_docstring_node(node: ast.stmt) -> bool:
    """Check if a statement node is a docstring (Expr wrapping a Constant string)."""
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _ast_detect_names(
    text: str,
    tree: ast.Module,
    aliases: dict[str, str],
    name_guides: dict[str, Guide],
) -> list[CheckMatch]:
    """Walk AST once, resolve Name/Attribute nodes through aliases, match against detect-names."""
    lines = text.splitlines()
    matches: list[CheckMatch] = []
    seen: set[tuple[int, str]] = set()

    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and _is_docstring_node(body[0]):
                ds = body[0]
                for ln in range(ds.lineno, ds.end_lineno + 1):
                    docstring_lines.add(ln)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Name, ast.Attribute)):
            continue
        if not isinstance(node.ctx, ast.Load):
            continue
        lineno = getattr(node, "lineno", None)
        if lineno is None or lineno in docstring_lines:
            continue

        fqn = _resolve_fqn(node, aliases)
        if fqn is None:
            continue

        for target_name, guide in name_guides.items():
            if fqn == target_name or fqn.startswith(target_name + "."):
                key = (lineno, guide.meta.id)
                if key in seen:
                    continue
                seen.add(key)
                source_line = lines[lineno - 1] if lineno <= len(lines) else ""
                matches.append(
                    CheckMatch(
                        line=lineno,
                        source_line=source_line,
                        guide_id=guide.meta.id,
                        guide_title=guide.meta.title,
                        category=guide.meta.category,
                        frequency=guide.meta.frequency,
                        snippet=guide.snippet,
                    )
                )
                break

    return matches


def _merge_matches(
    regex_matches: list[CheckMatch],
    ast_matches: list[CheckMatch],
) -> list[CheckMatch]:
    """Merge regex and AST matches, keeping one match per line (AST preferred)."""
    ast_by_line: dict[int, CheckMatch] = {}
    for m in ast_matches:
        if m.line not in ast_by_line:
            ast_by_line[m.line] = m

    result: list[CheckMatch] = []
    seen_lines: set[int] = set()

    for m in regex_matches:
        if m.line in ast_by_line:
            if m.line not in seen_lines:
                result.append(ast_by_line[m.line])
                seen_lines.add(m.line)
        else:
            if m.line not in seen_lines:
                result.append(m)
                seen_lines.add(m.line)

    for m in ast_matches:
        if m.line not in seen_lines:
            result.append(m)
            seen_lines.add(m.line)

    result.sort(key=lambda m: (m.line, FREQ_RANK.get(m.frequency, 2), m.guide_id))
    return result


def sanitize_line(text: str) -> str:
    text = _ANSI_RE.sub("", text)
    return _CTRL_RE.sub("", text)
