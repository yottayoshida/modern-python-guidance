from __future__ import annotations

from pathlib import Path

import pytest

from modern_python_guidance.frontmatter import GuideMeta
from modern_python_guidance.guide_index import Guide, GuideIndex, _extract_snippet, build_index
from modern_python_guidance.search import WEIGHT_BODY, search

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
        results = search(index, "pydantic")
        assert len(results) >= 2
        assert not any(r.fuzzy for r in results)
        same_score_groups: dict[float, list[str]] = {}
        for r in results:
            same_score_groups.setdefault(r.score, []).append(r.guide_id)
        for group in same_score_groups.values():
            assert group == sorted(group)


class TestSnippet:
    def test_all_guides_have_snippet(self, index):
        results = search(index, "python", limit=50)
        for r in results:
            guide = index.get(r.guide_id)
            assert guide is not None
            assert guide.snippet, f"{r.guide_id} has empty snippet"

    def test_all_guides_non_empty_snippet(self):
        idx = build_index(GUIDES_DIR)
        for guide_id, guide in idx.guides.items():
            assert guide.snippet, f"{guide_id} has empty snippet"

    def test_snippet_in_search_result(self, index):
        results = search(index, "pydantic validator")
        assert len(results) >= 1
        r = results[0]
        assert r.snippet
        assert "→" in r.snippet

    def test_snippet_exact_fixtures(self, index):
        fixtures = {
            "pydantic-v2-validators": (
                "from pydantic import BaseModel, validator, root_validator"
                " → "
                "from pydantic import BaseModel, field_validator, model_validator"
            ),
            "dataclass-modern": "@dataclass → @dataclass(frozen=True, slots=True, kw_only=True)",
            "use-builtin-generics": (
                "from typing import Dict, List, Optional, Set, Tuple"
                " → "
                "def process(items: list[str]) -> dict[str, int]:"
            ),
            "taskgroup-over-gather": (
                "results = await asyncio.gather( → async with asyncio.TaskGroup() as tg:"
            ),
        }
        for guide_id, expected in fixtures.items():
            guide = index.get(guide_id)
            assert guide is not None, f"{guide_id} not found"
            assert guide.snippet == expected, (
                f"{guide_id}: expected {expected!r}, got {guide.snippet!r}"
            )


class TestSnippetExtraction:
    def test_unequal_bad_longer(self):
        body = "## BAD\n```python\nline_a\nline_b\nline_c\n```\n## GOOD\n```python\nline_x\n```\n"
        snippet = _extract_snippet(body)
        assert snippet == "line_a → line_x"

    def test_unequal_good_longer(self):
        body = "## BAD\n```python\nline_a\n```\n## GOOD\n```python\nline_x\nline_y\nline_z\n```\n"
        snippet = _extract_snippet(body)
        assert snippet == "line_a → line_x"

    def test_late_differing_line(self):
        body = (
            "## BAD\n```python\nimport foo\nresult = old_call()\n```\n"
            "## GOOD\n```python\nimport foo\nresult = new_call()\n```\n"
        )
        snippet = _extract_snippet(body)
        assert snippet == "result = old_call() → result = new_call()"

    def test_diff_beyond_eight_lines(self):
        shared = "\n".join(f"line_{i}" for i in range(9))
        body = (
            f"## BAD\n```python\n{shared}\nold_call()\n```\n"
            f"## GOOD\n```python\n{shared}\nnew_call()\n```\n"
        )
        snippet = _extract_snippet(body)
        assert snippet == "old_call() → new_call()"

    def test_trailing_only_in_bad(self):
        body = "## BAD\n```python\nshared\nextra_bad\n```\n## GOOD\n```python\nshared\n```\n"
        snippet = _extract_snippet(body)
        assert snippet == "extra_bad"

    def test_trailing_only_in_good(self):
        body = "## BAD\n```python\nshared\n```\n## GOOD\n```python\nshared\nextra_good\n```\n"
        snippet = _extract_snippet(body)
        assert snippet == "extra_good"

    def test_all_lines_identical(self):
        body = "## BAD\n```python\nsame\n```\n## GOOD\n```python\nsame\n```\n"
        snippet = _extract_snippet(body)
        assert snippet == "same → same"

    def test_heading_boundary_not_prefix_match(self):
        body = (
            "## BADLY_NAMED\n```python\nwrong\n```\n"
            "## BAD\n```python\ncorrect_bad\n```\n"
            "## GOOD\n```python\ncorrect_good\n```\n"
        )
        snippet = _extract_snippet(body)
        assert snippet == "correct_bad → correct_good"

    def test_first_fence_only(self):
        body = (
            "## BAD\n```python\nfirst_bad\n```\n"
            "```python\nsecond_bad\n```\n"
            "## GOOD\n```python\nfirst_good\n```\n"
        )
        snippet = _extract_snippet(body)
        assert snippet == "first_bad → first_good"

    def test_no_bad_section(self):
        body = "## GOOD\n```python\ncode\n```\n"
        snippet = _extract_snippet(body)
        assert snippet == ""

    def test_no_good_section(self):
        body = "## BAD\n```python\ncode\n```\n"
        snippet = _extract_snippet(body)
        assert snippet == ""


class TestBodySearch:
    """Body text is indexed at WEIGHT_BODY=2, discoverable but below frontmatter."""

    def test_body_only_match_aiter_bytes(self, index):
        results = search(index, "aiter_bytes")
        assert len(results) >= 1
        assert results[0].guide_id == "httpx-streaming"
        assert not results[0].fuzzy

    def test_body_only_match_serialize_timestamp(self, index):
        results = search(index, "serialize_timestamp")
        assert len(results) >= 1
        assert results[0].guide_id == "pydantic-v2-serialization"

    def test_body_only_match_from_attributes(self, index):
        results = search(index, "from_attributes")
        ids = [r.guide_id for r in results]
        assert "pydantic-v2-config" in ids

    def test_code_fragment_with_parens(self, index):
        results = search(index, "aiter_bytes()")
        assert len(results) >= 1
        assert results[0].guide_id == "httpx-streaming"

    def test_code_fragment_with_equals(self, index):
        results = search(index, "from_attributes=True")
        ids = [r.guide_id for r in results]
        assert "pydantic-v2-config" in ids

    def test_body_score_below_frontmatter(self, index):
        results = search(index, "typing")
        assert results[0].guide_id == "use-builtin-generics"
        assert results[0].score >= 10

    def test_body_match_gets_frequency_boost(self, index):
        results = search(index, "aiter_bytes")
        r = results[0]
        assert r.score > 2.0

    def test_metadata_ranking_preserved(self, index):
        results = search(index, "typing")
        assert results[0].guide_id == "use-builtin-generics"

    def test_fuzzy_fallback_still_works(self, index):
        results = search(index, "genercs")
        assert len(results) > 0
        assert results[0].fuzzy is True


class TestBodySearchSynthetic:
    """Synthetic index tests for exact score verification — no real guide dependency."""

    @pytest.fixture
    def synthetic_index(self):
        meta = GuideMeta(
            id="synth",
            title="Synthetic Guide",
            category="testing",
            layer=1,
            tags=["unrelated_tag"],
            python=">=3.9",
            frequency="low",
        )
        guide = Guide(
            meta=meta,
            body="",
            source_path="synth.md",
            body_tokens=frozenset(
                ["target_api", "another_api", "datetime.utcnow", "datetime", "utcnow"]
            ),
        )
        return GuideIndex(guides={"synth": guide})

    def test_exact_body_only_score(self, synthetic_index):
        results = search(synthetic_index, "target_api")
        assert len(results) == 1
        assert results[0].score == WEIGHT_BODY

    def test_multiple_idents_score_additive(self, synthetic_index):
        results = search(synthetic_index, "target_api another_api")
        assert len(results) == 1
        assert results[0].score == WEIGHT_BODY * 2

    def test_dotted_query_matches_split_parts(self, synthetic_index):
        results = search(synthetic_index, "datetime.utcnow()")
        assert len(results) == 1
        ids_matched = {"datetime", "utcnow"}
        assert results[0].score == WEIGHT_BODY * len(ids_matched)

    def test_body_match_suppresses_fuzzy(self, synthetic_index):
        results = search(synthetic_index, "target_api")
        assert len(results) >= 1
        assert not results[0].fuzzy


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

    def test_limit_negative_clamps_to_1(self, index):
        results = search(index, "typing", limit=-1)
        assert len(results) == 1

    def test_limit_zero_clamps_to_1(self, index):
        results = search(index, "typing", limit=0)
        assert len(results) == 1
