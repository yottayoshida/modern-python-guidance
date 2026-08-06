from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import extract_design_md_keys

from modern_python_guidance.dependency_compat import DependencyContext, DependencyFact
from modern_python_guidance.guide_index import build_index
from modern_python_guidance.retrieve import retrieve, retrieve_json, suggest_ids

GUIDES_DIR = Path(__file__).parent.parent / "skills" / "modern-python-guidance" / "guides"


@pytest.fixture
def index():
    return build_index(GUIDES_DIR)


class TestRetrieve:
    def test_single_guide(self, index):
        results = retrieve(index, ["use-builtin-generics"])
        assert len(results) == 1
        r = results[0]
        assert r["id"] == "use-builtin-generics"
        assert r["title"] == "Use Built-in Generic Types Instead of typing Module"
        assert r["category"] == "typing"
        assert r["layer"] == 1
        assert r["python"] == ">=3.9"
        assert r["frequency"] == "high"
        assert r["version_match"] is True
        assert "## BAD" in r["content"]
        assert "## GOOD" in r["content"]
        assert r["token_estimate"] > 0
        assert r["source"].startswith("modern-python-guidance v")
        assert r["detection"] == {"status": "detectable", "methods": ["regex", "ast-name"]}

    def test_multiple_guides(self, index):
        results = retrieve(index, ["use-builtin-generics", "fastapi-lifespan"])
        assert len(results) == 2
        ids = [r["id"] for r in results]
        assert "use-builtin-generics" in ids
        assert "fastapi-lifespan" in ids

    def test_nonexistent_guide_skipped(self, index):
        results = retrieve(index, ["nonexistent", "use-builtin-generics"])
        assert len(results) == 1
        assert results[0]["id"] == "use-builtin-generics"

    def test_all_nonexistent(self, index):
        results = retrieve(index, ["foo", "bar"])
        assert results == []

    def test_version_match_false(self, index):
        results = retrieve(index, ["taskgroup-over-gather"], python_version="3.9")
        assert len(results) == 1
        assert results[0]["version_match"] is False

    def test_version_match_true(self, index):
        results = retrieve(index, ["taskgroup-over-gather"], python_version="3.11")
        assert len(results) == 1
        assert results[0]["version_match"] is True

    def test_explicit_id_is_returned_with_incompatible_dependency_status(self, index):
        context = DependencyContext(
            {
                ("package", "pydantic"): (
                    DependencyFact("package", "pydantic", "1.10.15", None, "uv.lock"),
                )
            }
        )

        result = retrieve(index, ["pydantic-v2-config"], dependency_context=context)[0]

        assert result["id"] == "pydantic-v2-config"
        assert "class Config:" in result["content"]
        assert result["dependency_requirements"] == {"packages": ["pydantic>=2"], "tools": []}
        assert result["dependency_compatibility"]["status"] == "incompatible"
        assert result["dependency_compatibility"]["evidence"][0]["version"] == "1.10.15"

    def test_advisory_only_guide_reports_detection_status(self, index):
        result = retrieve(index, ["dataclass-modern"])[0]

        assert result["detection"] == {"status": "advisory-only", "methods": []}


class TestRetrieveJSON:
    def test_valid_json(self, index):
        output = retrieve_json(index, ["use-builtin-generics"])
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["id"] == "use-builtin-generics"

    def test_existing_schema_keys_are_preserved_additively(self, index):
        output = retrieve_json(index, ["use-builtin-generics"])
        parsed = json.loads(output)
        assert extract_design_md_keys("retrieve") <= set(parsed[0].keys())

    def test_dependency_fields_are_json_serializable(self, index):
        context = DependencyContext(
            {
                ("package", "pydantic"): (
                    DependencyFact("package", "pydantic", "2.7", None, "uv.lock"),
                )
            }
        )

        output = retrieve_json(index, ["pydantic-v2-config"], dependency_context=context)
        parsed = json.loads(output)

        assert parsed[0]["dependency_compatibility"]["status"] == "confirmed"


class TestSuggestIds:
    def test_close_match(self, index):
        suggestions = suggest_ids(index, "builtin-generics")
        assert "use-builtin-generics" in suggestions

    def test_no_match(self, index):
        suggestions = suggest_ids(index, "zzz-totally-unknown")
        assert suggestions == []

    def test_max_three(self, index):
        suggestions = suggest_ids(index, "pydantic")
        assert len(suggestions) <= 3

    def test_case_insensitive(self, index):
        suggestions = suggest_ids(index, "USE-BUILTIN-GENERICS")
        assert "use-builtin-generics" in suggestions

    def test_long_id_truncated(self, index):
        long_id = "use-builtin-generics" + "-x" * 200
        suggestions = suggest_ids(index, long_id)
        assert isinstance(suggestions, list)

    def test_non_string_returns_empty(self, index):
        assert suggest_ids(index, 123) == []

    def test_empty_index(self):
        from modern_python_guidance.guide_index import GuideIndex

        empty = GuideIndex()
        suggestions = suggest_ids(empty, "anything")
        assert suggestions == []
