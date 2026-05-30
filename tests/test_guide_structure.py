"""Structural validation for all guide files.

Ensures every guide in skills/modern-python-guidance/guides/ conforms to:
- Valid frontmatter (parsed by parse_frontmatter)
- id matches filename, category matches parent directory
- Exactly 5 ## sections in order: BAD, GOOD, Why, <any>, References
- Code fences in BAD and GOOD sections
- Body starts with H1 title
- No duplicate IDs across all guides
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from modern_python_guidance.frontmatter import parse_frontmatter
from modern_python_guidance.guide_index import _find_guides_dir

GUIDES_DIR = _find_guides_dir()
EXPECTED_GUIDE_COUNT = 41

REQUIRED_HEADING_ORDER = {
    0: "BAD",
    1: "GOOD",
    2: "Why",
    4: "References",
}


def _collect_guides() -> list[Path]:
    return sorted(GUIDES_DIR.rglob("*.md"))


def _headings_outside_fences(body: str) -> list[str]:
    # Handles both ``` and ~~~ fences; guide_index._code_lines only handles ```
    headings = []
    in_fence = False
    for line in body.splitlines():
        stripped = line.strip()
        if re.match(r"^(`{3,}|~{3,})", stripped):
            in_fence = not in_fence
            continue
        if not in_fence and line.startswith("## "):
            headings.append(line[3:].strip())
    return headings


def _section_text(body: str, heading: str) -> str:
    # Not fence-aware: splits on \n## which could appear inside code fences.
    # Current guides have no ## at line start inside fences, so this is safe for now.
    parts = body.split(f"## {heading}\n", 1)
    if len(parts) < 2:
        return ""
    section = parts[1].split("\n## ", 1)[0]
    return section


_GUIDE_FILES = _collect_guides()
_GUIDE_IDS = [f"{f.parent.name}/{f.stem}" for f in _GUIDE_FILES]


@pytest.fixture(params=_GUIDE_FILES, ids=_GUIDE_IDS)
def guide_file(request: pytest.FixtureRequest) -> Path:
    return request.param


class TestGuideStructure:
    def test_parses_without_error(self, guide_file: Path):
        text = guide_file.read_text(encoding="utf-8")
        parse_frontmatter(text)

    def test_id_matches_filename(self, guide_file: Path):
        text = guide_file.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        assert meta.id == guide_file.stem, (
            f"frontmatter id '{meta.id}' != filename '{guide_file.stem}'"
        )

    def test_category_matches_dirname(self, guide_file: Path):
        text = guide_file.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        assert meta.category == guide_file.parent.name, (
            f"frontmatter category '{meta.category}' != dir '{guide_file.parent.name}'"
        )

    def test_section_headings(self, guide_file: Path):
        text = guide_file.read_text(encoding="utf-8")
        _, body = parse_frontmatter(text)
        headings = _headings_outside_fences(body)

        assert len(headings) == 5, f"expected 5 ## headings, got {len(headings)}: {headings}"
        for idx, expected in REQUIRED_HEADING_ORDER.items():
            assert headings[idx] == expected, (
                f"heading[{idx}] expected '{expected}', got '{headings[idx]}'"
            )

    def test_bad_good_have_code_fences(self, guide_file: Path):
        text = guide_file.read_text(encoding="utf-8")
        _, body = parse_frontmatter(text)
        for section_name in ("BAD", "GOOD"):
            section = _section_text(body, section_name)
            assert re.search(r"^(`{3,}|~{3,})", section, re.MULTILINE), (
                f"## {section_name} section has no code fence"
            )

    def test_body_starts_with_h1(self, guide_file: Path):
        text = guide_file.read_text(encoding="utf-8")
        _, body = parse_frontmatter(text)
        assert body.startswith("# "), "body does not start with H1 heading"


class TestGuideInventory:
    def test_no_duplicate_ids(self):
        seen: dict[str, Path] = {}
        for guide_file in _GUIDE_FILES:
            text = guide_file.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(text)
            assert meta.id not in seen, (
                f"duplicate id '{meta.id}': {seen[meta.id]} and {guide_file}"
            )
            seen[meta.id] = guide_file

    def test_guide_count(self):
        assert len(_GUIDE_FILES) == EXPECTED_GUIDE_COUNT, (
            f"expected {EXPECTED_GUIDE_COUNT} guides, found {len(_GUIDE_FILES)}"
        )
