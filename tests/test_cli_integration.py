"""End-to-end CLI integration tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import extract_design_md_keys

from modern_python_guidance import __version__

BIN = [sys.executable, "-m", "modern_python_guidance"]
REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [*BIN, *args],
        cwd=cwd,
        env=env,
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
        assert data[0]["target_python"] == {
            "version": "3.11",
            "source": "project.requires-python",
        }

    def test_search_auto_detects_pep621_and_filters(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "fixture"\nversion = "0"\nrequires-python = ">=3.9"\n'
        )
        r = run_cli("search", "asyncio taskgroup", "--format", "json", cwd=tmp_path)
        assert r.returncode == 0
        assert "taskgroup-over-gather" not in {item["id"] for item in json.loads(r.stdout)}

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
        assert extract_design_md_keys("search") <= set(data[0].keys())
        assert isinstance(data[0]["tags"], list)
        assert "→" in data[0]["snippet"]

    def test_search_reports_detection_metadata(self):
        r = run_cli("search", "typing list", "--format", "json")
        assert r.returncode == 0
        result = json.loads(r.stdout)[0]

        assert result["detection"] == {"status": "detectable", "methods": ["regex", "ast-name"]}

    def test_search_hides_proven_incompatible_dependencies_by_default(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "fixture"\nversion = "0"\ndependencies = ["pydantic==1.10.15"]\n'
        )
        r = run_cli(
            "search",
            "pydantic",
            "--project-dir",
            str(tmp_path),
            "--limit",
            "50",
            "--format",
            "json",
        )
        assert r.returncode == 0
        assert "pydantic-v2-config" not in {item["id"] for item in json.loads(r.stdout)}

    def test_search_include_incompatible_reports_dependency_status(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "fixture"\nversion = "0"\ndependencies = ["pydantic==1.10.15"]\n'
        )
        r = run_cli(
            "search",
            "pydantic",
            "--project-dir",
            str(tmp_path),
            "--include-incompatible",
            "--limit",
            "50",
            "--format",
            "json",
        )
        assert r.returncode == 0
        result = next(item for item in json.loads(r.stdout) if item["id"] == "pydantic-v2-config")
        assert result["dependency_compatibility"]["status"] == "incompatible"


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
        assert guide["target_python"] == {
            "version": "3.11",
            "source": "project.requires-python",
        }

    def test_retrieve_reports_detection_metadata(self):
        r = run_cli("retrieve", "dataclass-modern", "--format", "json")
        assert r.returncode == 0
        assert json.loads(r.stdout)[0]["detection"] == {
            "status": "advisory-only",
            "methods": [],
        }

    def test_retrieve_auto_detects_python_version_file(self, tmp_path: Path):
        (tmp_path / ".python-version").write_text("3.9\n")
        r = run_cli("retrieve", "taskgroup-over-gather", "--format", "json", cwd=tmp_path)
        assert r.returncode == 0
        guide = json.loads(r.stdout)[0]
        assert guide["version_match"] is False
        assert guide["target_python"] == {"version": "3.9", "source": ".python-version"}

    def test_retrieve_explicit_version_overrides_project(self, tmp_path: Path):
        (tmp_path / ".python-version").write_text("3.9\n")
        r = run_cli(
            "retrieve",
            "taskgroup-over-gather",
            "--python-version",
            "3.12",
            "--format",
            "json",
            cwd=tmp_path,
        )
        assert r.returncode == 0
        guide = json.loads(r.stdout)[0]
        assert guide["version_match"] is True
        assert guide["target_python"] == {"version": "3.12", "source": "explicit"}

    def test_retrieve_multiple(self):
        r = run_cli("retrieve", "use-builtin-generics,fastapi-lifespan", "--format", "json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert len(data) == 2

    def test_retrieve_nonexistent(self):
        r = run_cli("retrieve", "nonexistent", "--format", "json")
        assert r.returncode == 1

    def test_retrieve_not_found_envelope_keys(self):
        r = run_cli(
            "retrieve",
            "nonexistent,use-builtin-generics",
            "--format",
            "json",
        )
        assert r.returncode == 1
        data = json.loads(r.stdout)
        assert set(data.keys()) == extract_design_md_keys("retrieve", "envelope")
        assert set(data["not_found"][0].keys()) == extract_design_md_keys(
            "retrieve", "not_found_item"
        )

    def test_retrieve_existing_schema_is_preserved_additively(self):
        r = run_cli("retrieve", "use-builtin-generics", "--format", "json")
        data = json.loads(r.stdout)
        assert extract_design_md_keys("retrieve") <= set(data[0].keys())

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
        assert data[0]["target_python"] == {
            "version": "3.11",
            "source": "project.requires-python",
        }

    def test_list_auto_detects_poetry(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text('[tool.poetry.dependencies]\npython = "^3.10"\n')
        r = run_cli("list", "--format", "json", cwd=tmp_path)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data
        assert data[0]["target_python"] == {
            "version": "3.10",
            "source": "poetry.dependencies.python",
        }

    def test_list_stable_schema(self):
        r = run_cli("list", "--format", "json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert extract_design_md_keys("list") <= set(data[0].keys())

    def test_list_reports_detection_metadata(self):
        r = run_cli("list", "--format", "json")
        assert r.returncode == 0
        data = {item["id"]: item for item in json.loads(r.stdout)}

        assert data["use-builtin-generics"]["detection"] == {
            "status": "detectable",
            "methods": ["regex", "ast-name"],
        }
        assert data["dataclass-modern"]["detection"] == {
            "status": "advisory-only",
            "methods": [],
        }

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

    def test_list_dependency_override_filters_and_json_is_additive(self):
        r = run_cli("list", "--dependency-version", "package:pydantic=1.10.15", "--format", "json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "pydantic-v2-config" not in {item["id"] for item in data}
        assert "dependency_compatibility" in data[0]


class TestDetectVersion:
    def test_detect_default(self, tmp_path):
        r = run_cli("detect-version", "--project-dir", str(tmp_path))
        assert r.returncode == 0
        assert r.stdout.strip() == "3.11"

    def test_detect_json_reports_source(self, tmp_path):
        (tmp_path / ".python-version").write_text("3.12\n")
        r = run_cli("detect-version", "--project-dir", str(tmp_path), "--format", "json")
        assert r.returncode == 0
        assert json.loads(r.stdout) == {
            "python_version": "3.12",
            "source": ".python-version",
        }


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
        assert data["target_python"] == {
            "version": "3.11",
            "source": "project.requires-python",
        }

    def test_check_clean_file(self, tmp_path):
        p = tmp_path / "clean.py"
        p.write_text("x: list[str] = []\n")
        r = run_cli("check", str(p), "--format", "json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["summary"]["total_matches"] == 0
        coverage = data["summary"]["coverage"]
        assert coverage["catalog_guides"] == 41
        assert (
            coverage["detectable_guides"] + coverage["advisory_only_guides"]
            == coverage["applicable_guides"]
        )
        assert len(coverage["advisory_only_ids"]) == coverage["advisory_only_guides"]

    def test_check_human_reports_scope(self, tmp_path):
        p = tmp_path / "bad.py"
        p.write_text("from typing import List\n")

        r = run_cli("check", str(p), "--format", "human")

        assert r.returncode == 1
        assert "Check scope:" in r.stdout

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

    def test_check_project_v1_suppresses_pydantic_v2_and_unknown_is_annotated(self, tmp_path):
        p = tmp_path / "sample.py"
        p.write_text(
            "from pydantic import BaseModel, validator\n\n"
            "@validator('field')\n"
            "def validate(value):\n"
            "    return value\n"
        )
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "fixture"\nversion = "0"\ndependencies = ["pydantic==1.10.15"]\n'
        )
        v1 = run_cli("check", str(p), "--project-dir", str(tmp_path), "--format", "json")
        assert v1.returncode == 0
        assert "pydantic-v2-validators" not in v1.stdout

        (tmp_path / "pyproject.toml").write_text('[project]\nname = "fixture"\nversion = "0"\n')
        unknown = run_cli("check", str(p), "--project-dir", str(tmp_path), "--format", "json")
        assert unknown.returncode == 1
        match = next(
            item
            for item in json.loads(unknown.stdout)["matches"]
            if item["guide_id"] == "pydantic-v2-validators"
        )
        assert match["dependency_compatibility"]["status"] == "unknown"

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
        assert r.returncode == 0
        assert r.stderr == ""
        payload = json.loads(r.stdout)
        context = payload["hookSpecificOutput"]["additionalContext"]
        assert payload["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
        assert "mpg:" in context
        assert "use-builtin-generics" in context
        assert "Check scope:" in context
        # raw source line must never appear (T1: indirect prompt injection channel)
        assert "from typing import List" not in context

    def test_hook_py_clean(self, tmp_path):
        p = tmp_path / "clean.py"
        p.write_text("x: list[str] = []\n")
        stdin = json.dumps({"tool_input": {"file_path": str(p)}})
        r = self._run_hook(stdin)
        assert r.returncode == 0
        assert r.stdout == ""
        assert r.stderr == ""

    def test_hook_caps_surfaced_matches(self, tmp_path):
        """#152 Step 4: additionalContext surfaces at most 5 matches + a '+N more'
        summary, even when many more patterns are found (noise-bound per UX)."""
        p = tmp_path / "very_bad.py"
        p.write_text("from typing import List\n" * 7)
        stdin = json.dumps({"tool_input": {"file_path": str(p)}})
        r = self._run_hook(stdin)
        assert r.returncode == 0
        context = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        per_match_lines = [
            ln for ln in context.splitlines() if ln.startswith("mpg: use-builtin-generics (line")
        ]
        assert len(per_match_lines) == 5
        assert "+2 more" in context

    def test_hook_cta_uses_resolvable_interpreter(self, tmp_path):
        """#152 Step 4: the CTA must be runnable as-is, not a bare `mpg` that
        can be unresolvable on PATH in a venv-only install (#118 same class)."""
        p = tmp_path / "bad.py"
        p.write_text("from typing import List\n")
        stdin = json.dumps({"tool_input": {"file_path": str(p)}})
        r = self._run_hook(stdin)
        context = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        assert sys.executable in context
        assert "retrieve_guides" in context

    def test_hook_suppresses_proven_incompatible_and_qualifies_unknown(self, tmp_path):
        p = tmp_path / "bad.py"
        p.write_text("@validator('field')\ndef validate(value):\n    return value\n")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "fixture"\nversion = "0"\ndependencies = ["pydantic==1.10.15"]\n'
        )
        stdin = json.dumps({"tool_input": {"file_path": str(p)}})
        incompatible = self._run_hook(stdin)
        assert incompatible.returncode == 0
        assert incompatible.stdout == ""

        (tmp_path / "pyproject.toml").write_text('[project]\nname = "fixture"\nversion = "0"\n')
        unknown = self._run_hook(stdin)
        assert unknown.returncode == 0
        context = json.loads(unknown.stdout)["hookSpecificOutput"]["additionalContext"]
        assert "dependency compatibility unknown; verify before applying" in context
        assert "apply the modern form" not in context

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
        assert r.returncode == 0
        payload = json.loads(r.stdout)
        assert "mpg:" in payload["hookSpecificOutput"]["additionalContext"]

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
