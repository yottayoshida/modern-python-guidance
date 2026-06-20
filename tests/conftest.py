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

    pattern = rf"### JSON schema \({re.escape(section)}\)\n.*?\n```json\n(.*?)\n```"
    m = re.search(pattern, text, re.DOTALL)
    assert m, f"docs/design.md: {section} section not found"

    data = json.loads(m.group(1))
    if isinstance(data, list):
        assert data, f"docs/design.md: empty JSON array in {section} section"
        return set(data[0].keys()) - {"..."}
    return set(data.keys()) - {"..."}
