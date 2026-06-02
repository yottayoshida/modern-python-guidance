from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

from modern_python_guidance.frontmatter import GuideMeta
from modern_python_guidance.guide_index import (
    Guide,
    GuideIndex,
    _code_lines,
    _find_guides_dir,
    build_index,
)


def _raise_type_error(_pkg):
    raise TypeError("mocked")


def _make_guide_md(
    *,
    guide_id: str = "test-guide",
    title: str = "Test Guide",
    category: str = "testing",
    layer: int = 1,
    python: str = ">=3.9",
    frequency: str = "high",
    bad_code: str = "old_code()",
    good_code: str = "new_code()",
) -> str:
    return (
        f"---\n"
        f"id: {guide_id}\n"
        f"title: {title}\n"
        f"category: {category}\n"
        f"layer: {layer}\n"
        f"tags:\n"
        f"  - test\n"
        f"python: \"{python}\"\n"
        f"frequency: {frequency}\n"
        f"---\n"
        f"\n"
        f"## BAD\n"
        f"```python\n"
        f"{bad_code}\n"
        f"```\n"
        f"\n"
        f"## GOOD\n"
        f"```python\n"
        f"{good_code}\n"
        f"```\n"
    )


# ---------------------------------------------------------------------------
# GuideIndex dataclass methods
# ---------------------------------------------------------------------------


class TestGuideIndex:
    def test_len_empty(self):
        idx = GuideIndex()
        assert len(idx) == 0

    def test_len_with_entries(self):
        meta = GuideMeta(
            id="a", title="A", category="c", layer=1,
            tags=["t"], python=">=3.9", frequency="high",
        )
        idx = GuideIndex(guides={"a": Guide(meta=meta, body="", source_path="a.md")})
        assert len(idx) == 1

    def test_get_existing(self):
        meta = GuideMeta(
            id="a", title="A", category="c", layer=1,
            tags=["t"], python=">=3.9", frequency="high",
        )
        guide = Guide(meta=meta, body="body", source_path="a.md")
        idx = GuideIndex(guides={"a": guide})
        assert idx.get("a") is guide

    def test_get_missing(self):
        idx = GuideIndex()
        assert idx.get("nonexistent") is None

    def test_all_meta(self):
        meta = GuideMeta(
            id="a", title="A", category="c", layer=1,
            tags=["t"], python=">=3.9", frequency="high",
        )
        idx = GuideIndex(guides={"a": Guide(meta=meta, body="", source_path="a.md")})
        result = idx.all_meta()
        assert len(result) == 1
        assert result[0] is meta

    def test_categories_sorted_unique(self):
        def _meta(guide_id: str, cat: str) -> GuideMeta:
            return GuideMeta(
                id=guide_id, title=guide_id, category=cat, layer=1,
                tags=["t"], python=">=3.9", frequency="high",
            )

        idx = GuideIndex(guides={
            "b": Guide(meta=_meta("b", "zeta"), body="", source_path="b.md"),
            "a": Guide(meta=_meta("a", "alpha"), body="", source_path="a.md"),
            "c": Guide(meta=_meta("c", "alpha"), body="", source_path="c.md"),
        })
        assert idx.categories() == ["alpha", "zeta"]


# ---------------------------------------------------------------------------
# build_index
# ---------------------------------------------------------------------------


class TestBuildIndex:
    def test_happy_path(self, tmp_path: Path):
        (tmp_path / "guide-a.md").write_text(_make_guide_md(guide_id="guide-a"))
        (tmp_path / "guide-b.md").write_text(
            _make_guide_md(guide_id="guide-b", category="async")
        )
        idx = build_index(tmp_path)
        assert len(idx) == 2
        assert idx.get("guide-a") is not None
        assert idx.get("guide-b") is not None

    def test_nonexistent_directory(self, tmp_path: Path, caplog):
        missing = tmp_path / "does-not-exist"
        with caplog.at_level(logging.WARNING):
            idx = build_index(missing)
        assert len(idx) == 0
        assert "not found" in caplog.text

    def test_empty_directory(self, tmp_path: Path):
        idx = build_index(tmp_path)
        assert len(idx) == 0

    def test_duplicate_id_first_wins(self, tmp_path: Path, caplog):
        (tmp_path / "aaa.md").write_text(
            _make_guide_md(guide_id="dup", title="First")
        )
        (tmp_path / "bbb.md").write_text(
            _make_guide_md(guide_id="dup", title="Second")
        )
        (tmp_path / "ccc.md").write_text(
            _make_guide_md(guide_id="survivor", title="Survivor")
        )
        with caplog.at_level(logging.WARNING):
            idx = build_index(tmp_path)
        assert len(idx) == 2
        assert idx.get("dup").meta.title == "First"
        assert idx.get("survivor") is not None
        assert "Duplicate" in caplog.text

    def test_frontmatter_error_skipped(self, tmp_path: Path, caplog):
        (tmp_path / "bad.md").write_text("no frontmatter here")
        (tmp_path / "good.md").write_text(_make_guide_md(guide_id="good"))
        with caplog.at_level(logging.WARNING):
            idx = build_index(tmp_path)
        assert len(idx) == 1
        assert idx.get("good") is not None
        assert "Skipping" in caplog.text

    def test_generic_exception_skipped(self, tmp_path: Path, caplog):
        (tmp_path / "err.md").write_text("placeholder")
        (tmp_path / "ok.md").write_text(_make_guide_md(guide_id="ok"))

        original_read_text = Path.read_text

        def _patched_read_text(self, *args, **kwargs):
            if self.name == "err.md":
                raise RuntimeError("simulated read failure")
            return original_read_text(self, *args, **kwargs)

        with patch.object(Path, "read_text", _patched_read_text), caplog.at_level(logging.WARNING):
            idx = build_index(tmp_path)
        assert len(idx) == 1
        assert idx.get("ok") is not None
        assert "Unexpected error" in caplog.text

    def test_id_filename_mismatch(self, tmp_path: Path, caplog):
        (tmp_path / "wrong-name.md").write_text(
            _make_guide_md(guide_id="real-id")
        )
        with caplog.at_level(logging.WARNING):
            idx = build_index(tmp_path)
        assert len(idx) == 1
        assert idx.get("real-id") is not None
        assert idx.get("wrong-name") is None
        assert "mismatch" in caplog.text

    def test_nested_subdirectories(self, tmp_path: Path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "nested.md").write_text(_make_guide_md(guide_id="nested"))
        idx = build_index(tmp_path)
        assert len(idx) == 1
        assert idx.get("nested") is not None


# ---------------------------------------------------------------------------
# _code_lines (boundary cases only — _extract_snippet covered by test_search.py)
# ---------------------------------------------------------------------------


class TestCodeLines:
    def test_basic_extraction(self):
        body = "## BAD\n```python\nold()\nnew()\n```\n"
        assert _code_lines(body, "## BAD") == ["old()", "new()"]

    def test_tilde_fence_unsupported(self):
        body = "## BAD\n~~~python\nold()\n~~~\n"
        assert _code_lines(body, "## BAD") == []

    def test_heading_trailing_space_no_match(self):
        body = "## BAD \n```python\nold()\n```\n"
        assert _code_lines(body, "## BAD") == []

    def test_unclosed_fence_returns_all_lines(self):
        body = "## BAD\n```python\nline1\nline2\n"
        assert _code_lines(body, "## BAD") == ["line1", "line2"]

    def test_empty_code_block(self):
        body = "## BAD\n```python\n```\n"
        assert _code_lines(body, "## BAD") == []

    def test_multiple_fences_first_only(self):
        body = "## BAD\n```python\nfirst()\n```\n```python\nsecond()\n```\n"
        assert _code_lines(body, "## BAD") == ["first()"]


# ---------------------------------------------------------------------------
# _find_guides_dir fallbacks
# ---------------------------------------------------------------------------


class TestFindGuidesDir:
    def test_dev_fallback(self, monkeypatch):
        monkeypatch.setattr(
            "modern_python_guidance.guide_index.importlib.resources.files",
            _raise_type_error,
        )
        import modern_python_guidance.guide_index as gi_module

        repo_root = Path(__file__).resolve().parent.parent
        monkeypatch.setattr(
            gi_module,
            "__file__",
            str(repo_root / "src" / "modern_python_guidance" / "guide_index.py"),
        )
        result = _find_guides_dir()
        expected = repo_root / "skills" / "modern-python-guidance" / "guides"
        assert result == expected

    def test_relative_fallback(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "modern_python_guidance.guide_index.importlib.resources.files",
            _raise_type_error,
        )
        fake_file = tmp_path / "pkg" / "sub" / "guide_index.py"
        fake_file.parent.mkdir(parents=True)
        fake_file.touch()
        import modern_python_guidance.guide_index as gi_module

        monkeypatch.setattr(gi_module, "__file__", str(fake_file))
        result = _find_guides_dir()
        assert result == Path("skills") / "modern-python-guidance" / "guides"
