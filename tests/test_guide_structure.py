"""Structural validation for all guide files.

Ensures every guide in skills/modern-python-guidance/guides/ conforms to:
- Valid frontmatter (parsed by parse_frontmatter)
- id matches filename, category matches parent directory
- Exactly 5 ## sections in order: BAD, GOOD, Why, <any>, References
- Code fences in BAD and GOOD sections
- Body starts with H1 title
- No duplicate IDs across all guides
- detect_patterns: field is present, patterns compile, match BAD, not GOOD
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from modern_python_guidance.frontmatter import parse_frontmatter
from modern_python_guidance.guide_index import _code_lines, _find_guides_dir, build_index
from modern_python_guidance.setup_cmd import _build_rule_text

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


class TestRuleFileSync:
    """CI sync tests: rules/modern-python.md is thin and matches _build_rule_text()."""

    def _rule_path(self) -> Path:
        return GUIDES_DIR.parent.parent.parent / "rules" / "modern-python.md"

    def _rule_parts(self) -> tuple[str, str]:
        text = self._rule_path().read_text(encoding="utf-8")
        parts = text.split("---", 2)
        return parts[1].strip(), parts[2].lstrip("\n")

    def test_matches_build_rule_text(self):
        """rules/modern-python.md == _build_rule_text() output (SoT enforcement)."""
        actual = self._rule_path().read_text(encoding="utf-8")
        expected = _build_rule_text()
        assert actual == expected

    def test_frontmatter_has_paths(self):
        """rules/modern-python.md frontmatter contains expected paths patterns."""
        fm, _ = self._rule_parts()
        for pattern in [
            "**/*.py",
            "*.py",
            "**/pyproject.toml",
            "**/requirements*.txt",
            "**/setup.py",
            "**/setup.cfg",
            "**/.python-version",
            "**/Pipfile",
        ]:
            assert pattern in fm, f"missing path pattern: {pattern}"

    def test_frontmatter_no_name_or_description(self):
        """rules/modern-python.md frontmatter has NO name/description keys."""
        fm, _ = self._rule_parts()
        assert "name:" not in fm
        assert "description:" not in fm

    def test_thin_rule_has_guide_count(self):
        """Thin Rules body contains correct guide count."""
        _, body = self._rule_parts()
        assert f"All {EXPECTED_GUIDE_COUNT} guides" in body

    def test_thin_rule_has_mcp_pointer(self):
        """Thin Rules body references MCP tool or CLI retrieve."""
        _, body = self._rule_parts()
        assert "retrieve_guides" in body or "mpg retrieve" in body

    def test_thin_rule_has_all_guide_ids(self):
        """Every guide ID from the registry appears in thin Rules category index."""
        _, body = self._rule_parts()
        index = build_index()
        for guide_id in index.guides:
            assert f"`{guide_id}`" in body, f"guide ID missing from thin Rules: {guide_id}"


class TestDetectPatterns:
    def test_field_present(self, guide_file: Path):
        text = guide_file.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        assert meta.detect_patterns is not None, (
            f"{meta.id}: detect_patterns field is missing (must be list or empty list)"
        )

    def test_patterns_compile(self, guide_file: Path):
        text = guide_file.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        if not meta.detect_patterns:
            return
        for pat in meta.detect_patterns:
            try:
                re.compile(pat)
            except re.error as e:
                pytest.fail(f"{meta.id}: invalid regex {pat!r}: {e}")

    def test_patterns_match_bad_block(self, guide_file: Path):
        text = guide_file.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        if not meta.detect_patterns:
            return
        bad_lines = _code_lines(body, "## BAD")
        assert bad_lines, f"{meta.id}: BAD block is empty"
        for pat in meta.detect_patterns:
            compiled = re.compile(pat)
            matched = any(compiled.search(line) for line in bad_lines)
            assert matched, f"{meta.id}: pattern {pat!r} does not match any BAD line"

    def test_patterns_not_match_good_block(self, guide_file: Path):
        text = guide_file.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        if not meta.detect_patterns:
            return
        good_lines = _code_lines(body, "## GOOD")
        assert good_lines, f"{meta.id}: GOOD block is empty"
        for pat in meta.detect_patterns:
            compiled = re.compile(pat)
            for line in good_lines:
                assert not compiled.search(line), (
                    f"{meta.id}: pattern {pat!r} matches GOOD line: {line!r}"
                )


class TestPythonSpecifiers:
    def test_all_guides_have_valid_specifiers(self, guide_file: Path):
        from packaging.specifiers import SpecifierSet

        text = guide_file.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        SpecifierSet(meta.python)


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
