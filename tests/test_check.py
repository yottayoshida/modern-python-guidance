"""Tests for the check module — pattern matching engine."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from modern_python_guidance.check import (
    _MAX_FILE_SIZE,
    FREQ_RANK,
    CheckError,
    _auto_extract_patterns,
    _build_patterns,
    _get_patterns,
    _mask_strings,
    _parse_imports,
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


class TestStringLineFiltering:
    def test_docstring_not_matched(self, tmp_path: Path, index: GuideIndex):
        p = tmp_path / "docstring.py"
        p.write_text(
            "def example():\n"
            '    """Use datetime.utcnow() for timestamps.\n'
            "\n"
            "    Also from typing import List is common.\n"
            '    """\n'
            "    return 1\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        assert matches == []

    def test_inline_string_on_code_line_still_matched(self, tmp_path: Path, index: GuideIndex):
        p = tmp_path / "inline.py"
        p.write_text(
            'from typing import List\nx = "some string"\n',
            encoding="utf-8",
        )
        matches = check_file(p, index)
        ids = {m.guide_id for m in matches}
        assert "use-builtin-generics" in ids

    def test_tokenize_failure_falls_back(self, tmp_path: Path, index: GuideIndex):
        p = tmp_path / "broken.py"
        p.write_text(
            'from typing import List\nx = """unterminated\n',
            encoding="utf-8",
        )
        matches = check_file(p, index)
        ids = {m.guide_id for m in matches}
        assert "use-builtin-generics" in ids

    def test_indentation_error_falls_back(self, tmp_path: Path, index: GuideIndex):
        p = tmp_path / "indent.py"
        p.write_text(
            "from typing import List\nif True:\n    x = 1\n  y = 2\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        ids = {m.guide_id for m in matches}
        assert "use-builtin-generics" in ids

    def test_single_line_string_not_skipped(self, tmp_path: Path, index: GuideIndex):
        p = tmp_path / "singleline.py"
        p.write_text(
            "from typing import List  # 'example'\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        ids = {m.guide_id for m in matches}
        assert "use-builtin-generics" in ids


class TestFreqRank:
    def test_all_frequencies_covered(self):
        assert "high" in FREQ_RANK
        assert "medium" in FREQ_RANK
        assert "low" in FREQ_RANK
        assert FREQ_RANK["high"] < FREQ_RANK["medium"] < FREQ_RANK["low"]


class TestMaskStrings:
    """V-001 family: tokenize-based string/comment masking."""

    def test_single_line_string_masked(self):
        code = 'x = "from typing import List"\n'
        skip, masked = _mask_strings(code)
        assert 1 not in skip
        assert 1 in masked
        assert "from typing" not in masked[1]

    def test_multiline_string_interior_skipped(self):
        code = '"""\nfrom typing import List\n"""\n'
        skip, _masked = _mask_strings(code)
        assert 2 in skip

    def test_comment_masked(self):
        code = "x = 1  # datetime.utcnow()\n"
        _skip, masked = _mask_strings(code)
        assert 1 in masked
        assert "utcnow" not in masked[1]

    def test_tokenize_error_fallback(self):
        code = 'x = """unterminated\n'
        skip, masked = _mask_strings(code)
        assert skip == frozenset()
        assert masked == {}

    def test_code_outside_string_preserved(self):
        code = 'from typing import List; x = "hello"\n'
        skip, masked = _mask_strings(code)
        assert 1 not in skip
        assert 1 in masked
        assert "from typing import List" in masked[1]
        assert "hello" not in masked[1]

    def test_single_line_string_not_in_skip(self):
        """Mutation guard: single-line strings must use masked, not skip."""
        code = 'x = "from typing import List"\nreal_code = 1\n'
        skip, _masked = _mask_strings(code)
        assert 1 not in skip
        assert 2 not in skip

    def test_fstring_literal_masked(self):
        """f-string literal portion should be masked; expressions should remain."""
        code = 'x = f"prefix {some_var} suffix"\n'
        skip, masked = _mask_strings(code)
        assert 1 not in skip
        if 1 in masked:
            assert "prefix" not in masked[1]


class TestParseImports:
    def test_import_module(self):
        result = _parse_imports("import typing\n")
        assert result is not None
        aliases, _tree = result
        assert aliases == {"typing": "typing"}

    def test_from_import(self):
        result = _parse_imports("from typing import List\n")
        assert result is not None
        aliases, _tree = result
        assert aliases == {"List": "typing.List"}

    def test_aliased_import(self):
        result = _parse_imports("from typing import List as L\n")
        assert result is not None
        aliases, _tree = result
        assert aliases == {"L": "typing.List"}

    def test_module_alias(self):
        result = _parse_imports("import typing as t\n")
        assert result is not None
        aliases, _tree = result
        assert aliases == {"t": "typing"}

    def test_syntax_error_returns_none(self):
        assert _parse_imports("def f(\n") is None

    def test_from_import_nested(self):
        result = _parse_imports("from datetime import datetime\n")
        assert result is not None
        aliases, _tree = result
        assert aliases == {"datetime": "datetime.datetime"}


class TestStringLiteralFP:
    """V-001/V-002: string literals must not cause false positives."""

    def test_string_literal_no_match(self, tmp_path: Path, index: GuideIndex):
        """V-001: x = 'from typing import List' → 0 matches."""
        p = tmp_path / "v001.py"
        p.write_text('x = "from typing import List"\n', encoding="utf-8")
        matches = check_file(p, index)
        assert matches == []

    def test_string_with_real_code(self, tmp_path: Path, index: GuideIndex):
        """V-002: real import on different line still detected despite string."""
        p = tmp_path / "v002.py"
        p.write_text(
            'from typing import List\nx = "from typing import Dict"\n',
            encoding="utf-8",
        )
        matches = check_file(p, index)
        ids = {m.guide_id for m in matches}
        assert "use-builtin-generics" in ids
        assert len(matches) == 1
        assert matches[0].line == 1

    def test_inline_comment_no_match(self, tmp_path: Path, index: GuideIndex):
        """V-003: x = 1  # datetime.utcnow() → 0 matches."""
        p = tmp_path / "v003.py"
        p.write_text("x = 1  # datetime.utcnow()\n", encoding="utf-8")
        matches = check_file(p, index)
        assert matches == []


class TestAstQualifiedDetection:
    """V-012+: qualified/aliased forms detected via AST."""

    def test_qualified_typing_list(self, tmp_path: Path, index: GuideIndex):
        """V-012: import typing; x: typing.List[str]."""
        p = tmp_path / "v012.py"
        p.write_text(
            "import typing\n\nx: typing.List[str] = []\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        ids = {m.guide_id for m in matches}
        assert "use-builtin-generics" in ids

    def test_aliased_pydantic_validator(self, tmp_path: Path, index: GuideIndex):
        """V-013: from pydantic import validator as v; @v('name')."""
        p = tmp_path / "v013.py"
        p.write_text(
            "from pydantic import validator as v\n\n@v('name')\ndef check(cls, v): pass\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        ids = {m.guide_id for m in matches}
        assert "pydantic-v2-validators" in ids

    def test_qualified_pydantic_validator(self, tmp_path: Path, index: GuideIndex):
        """V-014: import pydantic; @pydantic.validator('name')."""
        p = tmp_path / "v014.py"
        p.write_text(
            "import pydantic\n\n@pydantic.validator('name')\ndef check(cls, v): pass\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        ids = {m.guide_id for m in matches}
        assert "pydantic-v2-validators" in ids

    def test_qualified_datetime_utcnow(self, tmp_path: Path, index: GuideIndex):
        """import datetime; datetime.datetime.utcnow()."""
        p = tmp_path / "dt_qualified.py"
        p.write_text(
            "import datetime\n\nnow = datetime.datetime.utcnow()\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        ids = {m.guide_id for m in matches}
        assert "datetime-utc" in ids

    def test_aliased_datetime_utcnow(self, tmp_path: Path, index: GuideIndex):
        """from datetime import datetime as dt; dt.utcnow()."""
        p = tmp_path / "dt_aliased.py"
        p.write_text(
            "from datetime import datetime as dt\n\nnow = dt.utcnow()\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        ids = {m.guide_id for m in matches}
        assert "datetime-utc" in ids

    def test_module_alias_asyncio_gather(self, tmp_path: Path, index: GuideIndex):
        """import asyncio as aio; aio.gather(...)."""
        p = tmp_path / "aio_alias.py"
        p.write_text(
            "import asyncio as aio\n\nasync def f():\n    await aio.gather(a(), b())\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        ids = {m.guide_id for m in matches}
        assert "taskgroup-over-gather" in ids

    def test_fstring_expression_detected_by_ast(self, tmp_path: Path, index: GuideIndex):
        """f-string: literal portion masked, but expression code detected by AST."""
        p = tmp_path / "fstring_ast.py"
        p.write_text(
            'from datetime import datetime\n\nx = f"now is {datetime.utcnow()}"\n',
            encoding="utf-8",
        )
        matches = check_file(p, index)
        ids = {m.guide_id for m in matches}
        assert "datetime-utc" in ids

    def test_ast_fallback_on_syntax_error(self, tmp_path: Path, index: GuideIndex):
        """V-020: AST parse failure → regex-only detection still works."""
        p = tmp_path / "v020.py"
        p.write_text(
            "from typing import List\ndef f(\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        ids = {m.guide_id for m in matches}
        assert "use-builtin-generics" in ids

    def test_python_version_filter_applies_to_ast(self, tmp_path: Path, index: GuideIndex):
        """AST detect-names also respects python_version filter."""
        p = tmp_path / "version_filter.py"
        p.write_text(
            "import typing\nx: typing.List[str] = []\n",
            encoding="utf-8",
        )
        matches_all = check_file(p, index)
        matches_38 = check_file(p, index, python_version="3.8")
        all_ids = {m.guide_id for m in matches_all}
        ids_38 = {m.guide_id for m in matches_38}
        assert "use-builtin-generics" in all_ids
        assert "use-builtin-generics" not in ids_38


class TestMergeAndDedup:
    """One match per line; AST preferred over regex on same line."""

    def test_one_match_per_line(self, tmp_path: Path, index: GuideIndex):
        p = tmp_path / "dedup.py"
        p.write_text(
            "from typing import List\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        assert len(matches) == 1

    def test_matches_sorted_by_line(self, tmp_path: Path, index: GuideIndex):
        p = tmp_path / "sorted.py"
        p.write_text(
            "from typing import List\n\nfrom datetime import datetime\nnow = datetime.utcnow()\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        lines = [m.line for m in matches]
        assert lines == sorted(lines)

    def test_ast_and_regex_same_line_dedup(self, tmp_path: Path, index: GuideIndex):
        """When regex and AST both match on the same line, only one result."""
        p = tmp_path / "both.py"
        p.write_text(
            "from typing import List\nimport typing\nx: typing.List[str] = []\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        line3_matches = [m for m in matches if m.line == 3]
        assert len(line3_matches) <= 1

    def test_ast_only_match_on_clean_line(self, tmp_path: Path, index: GuideIndex):
        """AST-only match (no regex) still appears in results."""
        p = tmp_path / "ast_only.py"
        p.write_text(
            "import typing\n\nx: typing.List[str] = []\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        ids = {m.guide_id for m in matches}
        assert "use-builtin-generics" in ids


class TestMaxFileSize:
    def test_large_file_rejected(self, tmp_path: Path, index: GuideIndex):
        p = tmp_path / "huge.py"
        p.write_bytes(b"x = 1\n" * (_MAX_FILE_SIZE // 6 + 1))
        with pytest.raises(CheckError, match="file too large"):
            check_file(p, index)

    def test_normal_file_accepted(self, tmp_path: Path, index: GuideIndex):
        p = tmp_path / "normal.py"
        p.write_text("x = 1\n" * 100, encoding="utf-8")
        matches = check_file(p, index)
        assert matches == []


class TestKnownLimitations:
    """Document known limitations — these are expected to NOT detect."""

    def test_wildcard_import_not_detected(self, tmp_path: Path, index: GuideIndex):
        """from typing import * → List usage not detected via AST."""
        p = tmp_path / "wildcard.py"
        p.write_text(
            "from typing import *\n\nx: List[str] = []\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        ast_on_line3 = [m for m in matches if m.line == 3]
        assert ast_on_line3 == []

    def test_reassignment_not_tracked(self, tmp_path: Path, index: GuideIndex):
        """v = validator; @v(...) — re-assignment not tracked."""
        p = tmp_path / "reassign.py"
        p.write_text(
            "from pydantic import validator\nv = validator\n\n@v('name')\ndef check(): pass\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        ast_on_decorator = [m for m in matches if m.line == 4]
        assert ast_on_decorator == []

    def test_store_context_not_detected(self, tmp_path: Path, index: GuideIndex):
        """Assignment target should not trigger detection (Codex P2 fix)."""
        p = tmp_path / "store.py"
        p.write_text(
            "from pydantic import validator\nvalidator = lambda x: x\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        store_matches = [m for m in matches if m.line == 2]
        assert store_matches == []

    def test_attribute_store_context_not_detected(self, tmp_path: Path, index: GuideIndex):
        """Qualified assignment target (typing.List = list) must not trigger."""
        p = tmp_path / "attr_store.py"
        p.write_text(
            "import typing\ntyping.List = list\n",
            encoding="utf-8",
        )
        matches = check_file(p, index)
        store_matches = [m for m in matches if m.line == 2]
        assert store_matches == []
