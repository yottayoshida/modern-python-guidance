"""Shared test helpers for modern-python-guidance."""

from __future__ import annotations

import json
import re
from pathlib import Path

_DESIGN_MD = Path(__file__).resolve().parent.parent / "docs" / "design.md"


def extract_design_md_keys(section: str, variant: str | None = None) -> set[str]:
    """Extract JSON field-name sets from docs/design.md schema examples.

    *section*: ``"search"``, ``"retrieve"``, or ``"list"``.

    *variant* (retrieve only):
      - ``None`` or ``"found"`` — keys of a found-guide element
      - ``"envelope"``         — top-level keys of the not-found envelope
      - ``"not_found_item"``   — keys of a ``not_found`` array element
    """
    if variant is not None and section != "retrieve":
        raise ValueError(f"variant is only supported for 'retrieve', got section={section!r}")

    text = _DESIGN_MD.read_text()

    if section == "retrieve":
        sec_m = re.search(
            r"### JSON schema \(retrieve\)\n(.*?)(?=### JSON schema|\Z)",
            text,
            re.DOTALL,
        )
        assert sec_m, "docs/design.md: retrieve section not found"

        blocks = re.findall(r"```json\n(.*?)\n```", sec_m.group(1), re.DOTALL)
        assert len(blocks) >= 2, "docs/design.md: expected >=2 JSON blocks in retrieve section"

        found_keys: set[str] | None = None
        envelope_keys: set[str] | None = None
        not_found_item_keys: set[str] | None = None

        for raw in blocks:
            data = json.loads(raw)
            if isinstance(data, list):
                assert data, "docs/design.md: empty JSON array in retrieve section"
                found_keys = set(data[0].keys()) - {"..."}
            elif isinstance(data, dict):
                envelope_keys = set(data.keys()) - {"..."}
                if data.get("not_found"):
                    not_found_item_keys = set(data["not_found"][0].keys()) - {"..."}

        if variant in (None, "found"):
            assert found_keys is not None, (
                "docs/design.md: no list-type JSON block in retrieve section"
            )
            return found_keys
        if variant == "envelope":
            assert envelope_keys is not None, (
                "docs/design.md: no dict-type JSON block in retrieve section"
            )
            return envelope_keys
        if variant == "not_found_item":
            assert not_found_item_keys is not None, (
                "docs/design.md: no not_found array in retrieve envelope"
            )
            return not_found_item_keys
        raise ValueError(f"unknown retrieve variant: {variant!r}")

    data = _schema_example(section)
    if isinstance(data, list):
        assert data, f"docs/design.md: empty JSON array in {section} section"
        return set(data[0].keys()) - {"..."}
    return set(data.keys()) - {"..."}


def _schema_example(section: str) -> object:
    """The first ``json`` block under ``### JSON schema (<section>)``, parsed.

    Shared by both comparison styles so the pattern lives in one place; two
    copies would let a change to the heading format fix one caller and leave
    the other silently finding nothing.
    """
    text = _DESIGN_MD.read_text()
    pattern = rf"### JSON schema \({re.escape(section)}\)\n.*?\n```json\n(.*?)\n```"
    m = re.search(pattern, text, re.DOTALL)
    assert m, f"docs/design.md: no JSON schema section for {section!r}"
    return json.loads(m.group(1))


def field_paths(node: object, prefix: str = "") -> set[str]:
    """Every field path in a JSON value, arrays collapsed to ``[]``.

    ``{"summary": {"coverage": {"catalog_guides": 41}}}`` becomes
    ``{"summary", "summary.coverage", "summary.coverage.catalog_guides"}``, and a
    list of objects contributes ``matches[].line`` rather than ``matches.0.line``.

    Top-level key sets stop at the outermost layer, which leaves whole nested
    objects unchecked: `check` output carries `target_python.{version,source}`
    and `matches[].dependency_compatibility.{status,reasons}`, and deleting
    either is invisible to a comparison of top-level names. Walking the whole
    value is what makes the comparison cover what the document actually shows.

    Every element of an array is walked, not just the first: a serializer that
    emits a field on the second match and not the first would otherwise slip
    past, and the union is what "every path this value contains" means. An
    empty array yields no element paths at all, so a fixture that produces one
    silently narrows what is compared — the caller has to supply input that
    populates the arrays it means to check.
    """
    paths: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "...":
                continue
            path = f"{prefix}.{key}" if prefix else key
            paths.add(path)
            paths |= field_paths(value, path)
    elif isinstance(node, list):
        for item in node:
            paths |= field_paths(item, f"{prefix}[]")
    return paths


def design_md_field_paths(section: str) -> set[str]:
    """The field paths of a ``### JSON schema (<section>)`` example.

    Read back against real output with ``==`` rather than ``<=``. The subset
    direction, used by `extract_design_md_keys` callers, passes when a field is
    deleted from design.md — the documented set shrinks and a smaller subset
    still fits. That direction cannot hold a frozen surface: the document is
    half of what is being compared.
    """
    return field_paths(_schema_example(section))


def design_md_section(heading: str) -> str:
    """The text of one ``###`` section, up to the next heading of any level.

    Scoped rather than file-wide because the labels this is used for appear in
    prose elsewhere: `## Version detection precedence` already lists all five
    version sources, so a file-wide search reports agreement even after the
    schema section that is supposed to declare them has lost one.
    """
    text = _DESIGN_MD.read_text()
    start = text.index(heading)
    rest = text[start + len(heading) :]
    end = re.search(r"\n#{2,3} ", rest)
    return rest[: end.start()] if end else rest


def design_md_enum(heading: str) -> set[str]:
    """The whitespace-separated names in the first untagged fenced block of a section.

    Fences are walked block by block rather than searched for directly. A
    pattern anchored on "fence, then newline" matches the *closing* fence of a
    ```json block just as well as an opening one, and then runs to the next
    fence — which returned the prose between the two blocks (``source is one
    of:``) instead of the list. Consuming whole blocks makes an opening fence
    identifiable, and the language tag is what distinguishes the list from the
    schema example beside it.
    """
    section = design_md_section(heading)
    for match in re.finditer(r"^```(\w*)\n(.*?)\n```$", section, re.DOTALL | re.MULTILINE):
        if not match.group(1):
            return set(match.group(2).split())
    raise AssertionError(f"docs/design.md: no untagged fenced list under {heading!r}")
