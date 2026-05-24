from __future__ import annotations

from pathlib import Path

import pytest

from modern_python_guidance.guide_index import build_index
from modern_python_guidance.search import search

GUIDES_DIR = Path(__file__).parent.parent / "skills" / "modern-python-guidance" / "guides"


@pytest.fixture
def index():
    return build_index(GUIDES_DIR)


class TestBasicSearch:
    def test_search_by_tag(self, index):
        results = search(index, "typing")
        assert len(results) >= 1
        assert results[0].guide_id == "use-builtin-generics"

    def test_search_by_alias(self, index):
        results = search(index, "typing.List")
        assert len(results) >= 1
        assert results[0].guide_id == "use-builtin-generics"

    def test_search_by_title_word(self, index):
        results = search(index, "lifespan")
        assert len(results) >= 1
        assert results[0].guide_id == "fastapi-lifespan"

    def test_search_by_category(self, index):
        results = search(index, "asyncio", category="async")
        assert all(r.meta.category == "async" for r in results)

    def test_search_returns_token_estimate(self, index):
        results = search(index, "typing")
        assert all(r.token_estimate > 0 for r in results)


class TestVersionFilter:
    def test_version_excludes_incompatible(self, index):
        results = search(index, "asyncio taskgroup", python_version="3.9")
        ids = [r.guide_id for r in results]
        assert "taskgroup-over-gather" not in ids

    def test_version_includes_compatible(self, index):
        results = search(index, "asyncio taskgroup", python_version="3.11")
        ids = [r.guide_id for r in results]
        assert "taskgroup-over-gather" in ids


class TestFuzzyFallback:
    def test_fuzzy_on_no_match(self, index):
        results = search(index, "genercs")
        assert len(results) > 0
        assert results[0].fuzzy is True

    def test_truly_irrelevant_query(self, index):
        results = search(index, "javascript react angular")
        assert all(r.fuzzy for r in results) or len(results) == 0


class TestDeterminism:
    def test_same_score_sorted_by_id(self, index):
        results = search(index, "python")
        ids = [r.guide_id for r in results]
        same_score_groups: dict[float, list[str]] = {}
        for r in results:
            same_score_groups.setdefault(r.score, []).append(r.guide_id)
        for group in same_score_groups.values():
            assert group == sorted(group)


class TestEdgeCases:
    def test_empty_query(self, index):
        results = search(index, "")
        assert results == []

    def test_long_query_truncated(self, index):
        results = search(index, "x " * 1000)
        assert isinstance(results, list)

    def test_limit(self, index):
        results = search(index, "python", limit=2)
        assert len(results) <= 2
