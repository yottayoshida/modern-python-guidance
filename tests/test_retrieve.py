from __future__ import annotations

import json
from pathlib import Path

import pytest

from modern_python_guidance.guide_index import build_index
from modern_python_guidance.retrieve import retrieve, retrieve_json

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


class TestRetrieveJSON:
    def test_valid_json(self, index):
        output = retrieve_json(index, ["use-builtin-generics"])
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["id"] == "use-builtin-generics"

    def test_stable_schema_keys(self, index):
        output = retrieve_json(index, ["use-builtin-generics"])
        parsed = json.loads(output)
        expected_keys = {
            "id", "title", "category", "layer", "python",
            "frequency", "version_match", "content", "token_estimate", "source",
        }
        assert set(parsed[0].keys()) == expected_keys
