"""End-to-end CLI integration tests."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

BIN = [sys.executable, "-m", "modern_python_guidance"]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*BIN, *args],
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestSearch:
    def test_search_returns_json(self):
        r = run_cli("search", "typing list", "--format", "json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["id"] == "use-builtin-generics"

    def test_search_human_format(self):
        r = run_cli("search", "typing", "--format", "human")
        assert r.returncode == 0
        assert "use-builtin-generics" in r.stdout

    def test_search_no_match_exits_1(self):
        r = run_cli("search", "qqqxxx999zzz", "--format", "json")
        assert r.returncode == 1

    def test_search_with_version_filter(self):
        r = run_cli("search", "asyncio taskgroup", "--python-version", "3.9", "--format", "json")
        data = json.loads(r.stdout)
        ids = [d["id"] for d in data]
        assert "taskgroup-over-gather" not in ids

    def test_search_with_category_filter(self):
        r = run_cli("search", "lifespan", "--category", "fastapi", "--format", "json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert all(d["category"] == "fastapi" for d in data)


class TestRetrieve:
    def test_retrieve_single(self):
        r = run_cli("retrieve", "use-builtin-generics", "--format", "json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert len(data) == 1
        guide = data[0]
        assert guide["id"] == "use-builtin-generics"
        assert "## BAD" in guide["content"]
        assert "## GOOD" in guide["content"]
        assert guide["source"].startswith("modern-python-guidance v")

    def test_retrieve_multiple(self):
        r = run_cli("retrieve", "use-builtin-generics,fastapi-lifespan", "--format", "json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert len(data) == 2

    def test_retrieve_nonexistent(self):
        r = run_cli("retrieve", "nonexistent", "--format", "json")
        assert r.returncode == 1

    def test_retrieve_stable_schema(self):
        r = run_cli("retrieve", "use-builtin-generics", "--format", "json")
        data = json.loads(r.stdout)
        expected_keys = {
            "id", "title", "category", "layer", "python",
            "frequency", "version_match", "content", "token_estimate", "source",
        }
        assert set(data[0].keys()) == expected_keys

    def test_retrieve_version_match_flag(self):
        r = run_cli("retrieve", "taskgroup-over-gather", "--python-version", "3.9", "--format", "json")
        data = json.loads(r.stdout)
        assert data[0]["version_match"] is False


class TestList:
    def test_list_json(self):
        r = run_cli("list", "--format", "json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert isinstance(data, list)
        assert len(data) >= 5

    def test_list_category_filter(self):
        r = run_cli("list", "--category", "typing", "--format", "json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert all(d["category"] == "typing" for d in data)

    def test_list_with_version_filter(self):
        r = run_cli("list", "--python-version", "3.9", "--format", "json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert isinstance(data, list)
        ids = [d["id"] for d in data]
        assert "taskgroup-over-gather" not in ids

    def test_list_with_bad_version(self):
        r = run_cli("list", "--python-version", "not.a.version", "--format", "json")
        assert r.returncode == 2

    def test_list_empty_result_exits_1(self):
        r = run_cli("list", "--category", "nonexistent-category", "--format", "json")
        assert r.returncode == 1

    def test_list_human_format(self):
        r = run_cli("list", "--format", "human")
        assert r.returncode == 0
        assert "[typing]" in r.stdout


class TestDetectVersion:
    def test_detect_default(self, tmp_path):
        r = run_cli("detect-version", "--project-dir", str(tmp_path))
        assert r.returncode == 0
        assert r.stdout.strip() == "3.11"


class TestPipeOutput:
    def test_no_ansi_in_json_output(self):
        r = run_cli("search", "typing", "--format", "json")
        assert "\x1b[" not in r.stdout

    def test_piped_default_is_json(self):
        r = run_cli("search", "typing")
        data = json.loads(r.stdout)
        assert isinstance(data, list)


class TestVersion:
    def test_version_flag(self):
        r = run_cli("--version")
        assert "modern-python-guidance" in r.stdout
        assert "0.1.0" in r.stdout
