"""Tests for the check module — pattern matching engine."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from modern_python_guidance.check import (
    FREQ_RANK,
    CheckError,
    _auto_extract_patterns,
    _build_patterns,
    _get_patterns,
    _read_file,
    _validate_file,
    check_file,
    sanitize_line,
)
from modern_python_guidance.guide_index import Guide, GuideIndex, build_index


@pytest.fixture
def sample_py(tmp_path: Path) -> Path:
    p = tmp_path / "sample.py"
    p.write_text(
        "from typing import Dict, List, Optional\n"
        "\n"
        "from datetime import datetime\n"
        "\n"
        "def example(items: List[str]) -> Dict[str, int]:\n"
        "    now = datetime.utcnow()\n"
        "    return {}\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def clean_py(tmp_path: Path) -> Path:
    p = tmp_path / "clean.py"
    p.write_text(
        "from datetime import UTC, datetime\n"
        "\n"
        "def example(items: list[str]) -> dict[str, int]:\n"
        "    now = datetime.now(UTC)\n"
        "    return {}\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def index() -> GuideIndex:
    return build_index()


class TestCheckFile:
    def test_detects_patterns(self, sample_py: Path, index: GuideIndex):
        matches = check_file(sample_py, index)
        assert len(matches) >= 1
        guide_ids = {m.guide_id for m in matches}
        assert "datetime-utc" in guide_ids

    def test_clean_file_no_matches(self, clean_py: Path, index: GuideIndex):
        matches = check_file(clean_py, index)
        assert matches == []

    def test_empty_file(self, tmp_path: Path, index: GuideIndex):
        p = tmp_path / "empty.py"
        p.write_text("", encoding="utf-8")
        matches = check_file(p, index)
        assert matches == []

    def test_comments_skipped(self, tmp_path: Path, index: GuideIndex):
        p = tmp_path / "commented.py"
        p.write_text("# from typing import List\n", encoding="utf-8")
        matches = check_file(p, index)
        assert matches == []

    def test_blank_lines_skipped(self, tmp_path: Path, index: GuideIndex):
        p = tmp_path / "blanks.py"
        p.write_text("\n\n\n", encoding="utf-8")
        matches = check_file(p, index)
        assert matches == []

    def test_first_match_wins(self, tmp_path: Path, index: GuideIndex):
        p = tmp_path / "overlap.py"
        p.write_text("from typing import Dict, List, Optional\n", encoding="utf-8")
        matches = check_file(p, index)
        assert len(matches) == 1

    def test_match_fields(self, sample_py: Path, index: GuideIndex):
        matches = check_file(sample_py, index)
        utc_matches = [m for m in matches if m.guide_id == "datetime-utc"]
        assert len(utc_matches) == 1
        m = utc_matches[0]
        assert m.line == 6
        assert "utcnow" in m.source_line
        assert m.guide_title
        assert m.category == "stdlib"
        assert m.frequency == "high"

    def test_python_version_filter(self, tmp_path: Path, index: GuideIndex):
        p = tmp_path / "py38.py"
        p.write_text("from typing import Dict, List\n", encoding="utf-8")
        matches_all = check_file(p, index)
        matches_38 = check_file(p, index, python_version="3.8")
        assert len(matches_38) <= len(matches_all)


class TestValidateFile:
    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(CheckError, match="file not found"):
            _validate_file(tmp_path / "nonexistent.py")

    def test_directory_rejected(self, tmp_path: Path):
        with pytest.raises(CheckError, match="not a file"):
            _validate_file(tmp_path)


class TestReadFile:
    def test_binary_file_rejected(self, tmp_path: Path):
        p = tmp_path / "binary.bin"
        p.write_bytes(b"hello\x00world")
        with pytest.raises(CheckError, match="binary file"):
            _read_file(p)

    def test_utf8_file(self, tmp_path: Path):
        p = tmp_path / "utf8.py"
        p.write_text("# UTF-8 content: cafe\n", encoding="utf-8")
        text = _read_file(p)
        assert "cafe" in text

    def test_non_utf8_replacement(self, tmp_path: Path):
        p = tmp_path / "latin.py"
        p.write_bytes(b"name = 'caf\xe9'\n")
        text = _read_file(p)
        assert "name" in text


class TestBuildPatterns:
    def test_returns_compiled_patterns(self, index: GuideIndex):
        patterns = _build_patterns(index)
        assert len(patterns) > 0
        for compiled, guide in patterns:
            assert isinstance(compiled, re.Pattern)
            assert isinstance(guide, Guide)

    def test_sorted_by_layer_then_freq(self, index: GuideIndex):
        patterns = _build_patterns(index)
        prev_key = (0, 0)
        for _compiled, guide in patterns:
            key = (guide.meta.layer, FREQ_RANK.get(guide.meta.frequency, 2))
            assert key >= prev_key
            prev_key = key

    def test_python_version_filter(self, index: GuideIndex):
        all_patterns = _build_patterns(index)
        filtered = _build_patterns(index, python_version="3.8")
        assert len(filtered) <= len(all_patterns)


class TestGetPatterns:
    def test_curated_patterns_used(self, index: GuideIndex):
        guide = index.get("use-builtin-generics")
        assert guide is not None
        patterns = _get_patterns(guide)
        assert len(patterns) >= 1
        assert any("List" in p for p in patterns)

    def test_opted_out_returns_empty(self, index: GuideIndex):
        guide = index.get("override-decorator")
        assert guide is not None
        patterns = _get_patterns(guide)
        assert patterns == []


class TestAutoExtractPatterns:
    def test_extracts_imports(self, index: GuideIndex):
        guide = index.get("use-builtin-generics")
        assert guide is not None
        patterns = _auto_extract_patterns(guide)
        assert len(patterns) >= 1
        assert any(
            re.compile(p).search("from typing import Dict, List, Optional, Set, Tuple")
            for p in patterns
        )

    def test_extracts_decorators(self, index: GuideIndex):
        guide = index.get("pydantic-v2-validators")
        assert guide is not None
        patterns = _auto_extract_patterns(guide)
        assert len(patterns) >= 1
        assert any(re.compile(p).search("@validator(") for p in patterns)


class TestSanitizeLine:
    def test_strips_ansi_escapes(self):
        assert sanitize_line("\x1b[31mred\x1b[0m") == "red"

    def test_strips_control_chars(self):
        assert sanitize_line("hello\x00world") == "helloworld"

    def test_preserves_tab_and_newline(self):
        assert sanitize_line("hello\tworld\n") == "hello\tworld\n"

    def test_normal_text_unchanged(self):
        text = "from typing import List"
        assert sanitize_line(text) == text


class TestEdgeCases:
    def test_long_line_skipped(self, tmp_path: Path, index: GuideIndex):
        p = tmp_path / "long.py"
        p.write_text("x = " + "a" * 11000 + "\nfrom typing import List\n", encoding="utf-8")
        matches = check_file(p, index)
        ids = {m.guide_id for m in matches}
        assert "use-builtin-generics" in ids or any("typing" in m.guide_id for m in matches)

    def test_no_patterns_returns_empty(self, tmp_path: Path):
        p = tmp_path / "sample.py"
        p.write_text("x = 1\n", encoding="utf-8")
        empty_index = GuideIndex()
        matches = check_file(p, empty_index)
        assert matches == []

    def test_auto_extract_fallback(self):
        from modern_python_guidance.frontmatter import GuideMeta

        meta = GuideMeta(
            id="test",
            title="Test",
            category="test",
            layer=1,
            tags=["test"],
            python=">=3.9",
            frequency="high",
            detect_patterns=None,
        )
        bad_body = (
            "## BAD\n\n```python\nimport os\n@decorator\n"
            "def f(): pass\n```\n\n## GOOD\n\n```python\npass\n```\n"
        )
        guide = Guide(
            meta=meta,
            body=bad_body,
            source_path="test.md",
            snippet="test",
        )
        patterns = _get_patterns(guide)
        assert len(patterns) >= 1

    def test_invalid_regex_skipped(self):
        from modern_python_guidance.frontmatter import GuideMeta

        meta = GuideMeta(
            id="bad-regex",
            title="Bad Regex",
            category="test",
            layer=1,
            tags=["test"],
            python=">=3.9",
            frequency="high",
            detect_patterns=["[invalid"],
        )
        guide = Guide(
            meta=meta,
            body="## BAD\n```python\n[invalid\n```\n## GOOD\n```python\npass\n```\n",
            source_path="test.md",
            snippet="test",
        )
        index = GuideIndex(guides={"bad-regex": guide})
        patterns = _build_patterns(index)
        assert len(patterns) == 0


class TestFreqRank:
    def test_all_frequencies_covered(self):
        assert "high" in FREQ_RANK
        assert "medium" in FREQ_RANK
        assert "low" in FREQ_RANK
        assert FREQ_RANK["high"] < FREQ_RANK["medium"] < FREQ_RANK["low"]
