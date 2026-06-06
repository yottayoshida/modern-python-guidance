"""End-to-end CLI integration tests."""

from __future__ import annotations

import json
import subprocess
import sys

from modern_python_guidance import __version__

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

    def test_search_enriched_keys(self):
        r = run_cli("search", "pydantic validator", "--format", "json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        expected_keys = {
            "id",
            "title",
            "category",
            "layer",
            "tags",
            "python",
            "frequency",
            "score",
            "token_estimate",
            "fuzzy",
            "snippet",
        }
        assert set(data[0].keys()) == expected_keys
        assert isinstance(data[0]["tags"], list)
        assert "→" in data[0]["snippet"]


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
            "id",
            "title",
            "category",
            "layer",
            "python",
            "frequency",
            "version_match",
            "content",
            "token_estimate",
            "source",
        }
        assert set(data[0].keys()) == expected_keys

    def test_retrieve_version_match_flag(self):
        r = run_cli(
            "retrieve",
            "taskgroup-over-gather",
            "--python-version",
            "3.9",
            "--format",
            "json",
        )
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


class TestCheck:
    def test_check_finds_patterns(self, tmp_path):
        p = tmp_path / "bad.py"
        p.write_text("from typing import List\nimport pickle\n")
        r = run_cli("check", str(p), "--format", "json")
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert data["summary"]["total_matches"] >= 2
        ids = data["summary"]["guide_ids"]
        assert "no-pickle" in ids

    def test_check_clean_file(self, tmp_path):
        p = tmp_path / "clean.py"
        p.write_text("x: list[str] = []\n")
        r = run_cli("check", str(p), "--format", "json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["summary"]["total_matches"] == 0

    def test_check_exit_zero(self, tmp_path):
        p = tmp_path / "bad.py"
        p.write_text("from typing import List\n")
        r = run_cli("check", str(p), "--exit-zero", "--format", "json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["summary"]["total_matches"] >= 1

    def test_check_human_format(self, tmp_path):
        p = tmp_path / "bad.py"
        p.write_text("from typing import List\n")
        r = run_cli("check", str(p), "--format", "human")
        assert r.returncode == 1
        assert "outdated pattern" in r.stdout

    def test_check_json_schema(self, tmp_path):
        p = tmp_path / "sample.py"
        p.write_text("import pickle\n")
        r = run_cli("check", str(p), "--format", "json")
        data = json.loads(r.stdout)
        assert "file" in data
        assert "mpg_version" in data
        assert "matches" in data
        assert "summary" in data
        assert "total_matches" in data["summary"]
        assert "unique_guides" in data["summary"]
        assert "guide_ids" in data["summary"]
        if data["matches"]:
            m = data["matches"][0]
            for key in (
                "line",
                "source_line",
                "guide_id",
                "guide_title",
                "category",
                "frequency",
                "snippet",
            ):
                assert key in m

    def test_check_file_not_found(self, tmp_path):
        r = run_cli("check", str(tmp_path / "nonexistent.py"), "--format", "json")
        assert r.returncode == 2

    def test_check_python_version_filter(self, tmp_path):
        p = tmp_path / "sample.py"
        p.write_text("from __future__ import annotations\n")
        r_all = run_cli("check", str(p), "--format", "json")
        r_old = run_cli("check", str(p), "--python-version", "3.11", "--format", "json")
        all_matches = json.loads(r_all.stdout)["summary"]["total_matches"]
        old_matches = json.loads(r_old.stdout)["summary"]["total_matches"]
        assert old_matches <= all_matches

    def test_check_quiet_clean_file(self, tmp_path):
        p = tmp_path / "clean.py"
        p.write_text("x: list[str] = []\n")
        r = run_cli("check", str(p), "--quiet", "--format", "human")
        assert r.returncode == 0
        assert r.stdout == ""
        assert r.stderr == ""

    def test_check_quiet_with_matches(self, tmp_path):
        p = tmp_path / "bad.py"
        p.write_text("from typing import List\n")
        r = run_cli("check", str(p), "--quiet", "--format", "human")
        assert r.returncode == 1
        assert "outdated pattern" in r.stdout


class TestHook:
    def _run_hook(self, stdin_data: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*BIN, "hook", "claude-post-tool-use"],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_hook_py_with_matches(self, tmp_path):
        p = tmp_path / "bad.py"
        p.write_text("from typing import List\n")
        stdin = json.dumps({"tool_input": {"file_path": str(p)}})
        r = self._run_hook(stdin)
        assert r.returncode == 2
        assert "mpg:" in r.stderr
        assert r.stdout == ""

    def test_hook_py_clean(self, tmp_path):
        p = tmp_path / "clean.py"
        p.write_text("x: list[str] = []\n")
        stdin = json.dumps({"tool_input": {"file_path": str(p)}})
        r = self._run_hook(stdin)
        assert r.returncode == 0
        assert r.stdout == ""
        assert r.stderr == ""

    def test_hook_non_py(self, tmp_path):
        p = tmp_path / "file.js"
        p.write_text("const x = 1;\n")
        stdin = json.dumps({"tool_input": {"file_path": str(p)}})
        r = self._run_hook(stdin)
        assert r.returncode == 0

    def test_hook_missing_file(self):
        stdin = json.dumps({"tool_input": {"file_path": "/nonexistent/test.py"}})
        r = self._run_hook(stdin)
        assert r.returncode == 0

    def test_hook_malformed_json(self):
        r = self._run_hook("{bad json")
        assert r.returncode == 0

    def test_hook_missing_keys(self):
        r = self._run_hook(json.dumps({"other": "data"}))
        assert r.returncode == 0

    def test_hook_uppercase_py(self, tmp_path):
        p = tmp_path / "bad.PY"
        p.write_text("from typing import List\n")
        stdin = json.dumps({"tool_input": {"file_path": str(p)}})
        r = self._run_hook(stdin)
        assert r.returncode == 2
        assert "mpg:" in r.stderr

    def test_hook_bare_no_subcommand(self):
        r = subprocess.run(
            [*BIN, "hook"],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert r.returncode == 2
        assert "available hooks" in r.stderr


class TestVersion:
    def test_version_flag(self):
        r = run_cli("--version")
        assert "modern-python-guidance" in r.stdout
        assert __version__ in r.stdout
