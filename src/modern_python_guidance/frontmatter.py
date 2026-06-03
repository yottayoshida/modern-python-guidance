"""Strict YAML-subset frontmatter parser for guide files.

Supports only:
  - key: value (string, quoted string, integer)
  - key:\\n  - item\\n  - item (indented list)

Rejects all other YAML constructs with FrontmatterError + line number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_KEY_RE = re.compile(r"^([a-z][a-z0-9_-]*)\s*:\s*(.*)")
_LIST_ITEM_RE = re.compile(r"^  - (.+)")
_FENCE = "---"

REQUIRED_FIELDS = frozenset({"id", "title", "category", "layer", "tags", "python", "frequency"})
VALID_FREQUENCIES = frozenset({"high", "medium", "low"})


class FrontmatterError(Exception):
    def __init__(self, message: str, line: int | None = None):
        self.line = line
        prefix = f"line {line}: " if line is not None else ""
        super().__init__(f"{prefix}{message}")


@dataclass
class GuideMeta:
    id: str
    title: str
    category: str
    layer: int
    tags: list[str]
    python: str
    frequency: str
    aliases: list[str] = field(default_factory=list)
    pep: list[int] = field(default_factory=list)
    detect_patterns: list[str] | None = None


def parse_frontmatter(text: str) -> tuple[GuideMeta, str]:
    lines = text.split("\n")

    if not lines or lines[0].strip() != _FENCE:
        raise FrontmatterError("file must start with ---", line=1)

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FENCE:
            end_idx = i
            break

    if end_idx is None:
        raise FrontmatterError("closing --- not found")

    raw = _parse_raw(lines[1:end_idx])
    meta = _build_meta(raw)
    body = "\n".join(lines[end_idx + 1 :]).strip()
    return meta, body


def _parse_raw(lines: list[str]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_key: str | None = None

    for i, line in enumerate(lines, start=2):
        if not line.strip():
            continue

        list_match = _LIST_ITEM_RE.match(line)
        if list_match:
            if current_key is None:
                raise FrontmatterError("list item without preceding key", line=i)
            if not isinstance(data[current_key], list):
                raise FrontmatterError(f"list item for non-list key '{current_key}'", line=i)
            data[current_key].append(_parse_scalar(list_match.group(1).strip()))
            continue

        key_match = _KEY_RE.match(line)
        if key_match:
            key = key_match.group(1)
            value_str = key_match.group(2).strip()

            if key in data:
                raise FrontmatterError(f"duplicate key '{key}'", line=i)

            if value_str:
                data[key] = _parse_scalar(value_str)
                current_key = None
            else:
                data[key] = []
                current_key = key
            continue

        raise FrontmatterError(f"unsupported syntax: {line!r}", line=i)

    return data


def _parse_scalar(value: str) -> str | int:
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]

    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]

    if value.isascii() and value.isdigit():
        return int(value)

    return value


def _build_meta(raw: dict[str, Any]) -> GuideMeta:
    missing = REQUIRED_FIELDS - raw.keys()
    if missing:
        raise FrontmatterError(f"missing required fields: {', '.join(sorted(missing))}")

    for str_field in ("id", "title", "category", "python", "frequency"):
        if isinstance(raw[str_field], list):
            raise FrontmatterError(f"'{str_field}' must be a scalar value, not a list")

    freq = raw["frequency"]
    if freq not in VALID_FREQUENCIES:
        raise FrontmatterError(f"invalid frequency '{freq}', must be one of {VALID_FREQUENCIES}")

    layer = raw["layer"]
    if not isinstance(layer, int) or layer not in (1, 2, 3):
        raise FrontmatterError(f"layer must be 1, 2, or 3, got {layer!r}")

    pep_raw = raw.get("pep")
    if pep_raw is None:
        pep = []
    elif isinstance(pep_raw, int):
        pep = [pep_raw]
    elif isinstance(pep_raw, list):
        try:
            pep = [int(p) for p in pep_raw]
        except (ValueError, TypeError) as e:
            raise FrontmatterError(f"pep list items must be integers: {e}") from e
    else:
        raise FrontmatterError(f"pep must be int or list of ints, got {pep_raw!r}")

    aliases_raw = raw.get("aliases", [])
    if not isinstance(aliases_raw, list):
        raise FrontmatterError(f"aliases must be a list, got {aliases_raw!r}")

    tags = raw["tags"]
    if not isinstance(tags, list) or not tags:
        raise FrontmatterError("tags must be a non-empty list")

    detect_raw = raw.get("detect-patterns")
    if detect_raw is None:
        detect_patterns = None
    elif isinstance(detect_raw, list):
        detect_patterns = [str(p) for p in detect_raw]
        for p in detect_patterns:
            try:
                re.compile(p)
            except re.error as e:
                raise FrontmatterError(f"invalid regex in detect-patterns: {p!r}: {e}") from e
    else:
        raise FrontmatterError(f"detect-patterns must be a list, got {detect_raw!r}")

    return GuideMeta(
        id=str(raw["id"]),
        title=str(raw["title"]),
        category=str(raw["category"]),
        layer=layer,
        tags=[str(t) for t in tags],
        python=str(raw["python"]),
        frequency=freq,
        aliases=[str(a) for a in aliases_raw],
        pep=pep,
        detect_patterns=detect_patterns,
    )
