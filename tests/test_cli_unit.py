"""In-process unit tests for cli.py — direct function calls for coverage."""

from __future__ import annotations

import json
import sys
from unittest.mock import patch

import pytest

from modern_python_guidance.cli import _resolve_format, main


class TestMainDispatch:
    def test_no_command_exits_2(self, capsys):
        with pytest.raises(SystemExit, match="2"):
            main(argv=[])

    def test_version_flag(self, capsys):
        from modern_python_guidance import __version__

        with pytest.raises(SystemExit, match="0"):
            main(argv=["--version"])
        assert __version__ in capsys.readouterr().out

    def test_invalid_python_version_exits(self, capsys):
        with pytest.raises(SystemExit, match="2"):
            main(argv=["search", "typing", "--python-version", "abc"])

    def test_broken_pipe_exits_0(self, monkeypatch):
        def raise_broken_pipe(*_a, **_kw):
            raise BrokenPipeError

        monkeypatch.setattr("modern_python_guidance.cli.do_search", raise_broken_pipe)
        with pytest.raises(SystemExit, match="0"):
            main(argv=["search", "typing"])


class TestResolveFormat:
    def test_explicit_json(self):
        ns = _make_ns(format="json")
        assert _resolve_format(ns) == "json"

    def test_explicit_human(self):
        ns = _make_ns(format="human")
        assert _resolve_format(ns) == "human"

    def test_auto_tty(self, monkeypatch):
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        ns = _make_ns(format=None)
        assert _resolve_format(ns) == "human"

    def test_auto_pipe(self, monkeypatch):
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
        ns = _make_ns(format=None)
        assert _resolve_format(ns) == "json"


class TestCmdSearch:
    def test_json_output(self, capsys):
        main(argv=["search", "typing list", "--format", "json"])
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_human_output(self, capsys):
        main(argv=["search", "typing", "--format", "human"])
        out = capsys.readouterr().out
        assert "use-builtin-generics" in out

    def test_no_match_exits_1(self, capsys):
        with pytest.raises(SystemExit, match="1"):
            main(argv=["search", "qqqxxx999zzz", "--format", "json"])

    def test_no_match_human_exits_1(self, capsys):
        with pytest.raises(SystemExit, match="1"):
            main(argv=["search", "qqqxxx999zzz", "--format", "human"])
        assert "No guides found" in capsys.readouterr().out

    def test_fuzzy_marker(self, capsys):
        main(argv=["search", "typng", "--format", "human"])
        out = capsys.readouterr().out
        assert "(fuzzy)" in out or "use-builtin-generics" in out

    def test_category_filter(self, capsys):
        main(argv=["search", "typing", "--category", "typing", "--format", "json"])
        data = json.loads(capsys.readouterr().out)
        assert data
        for item in data:
            assert item["category"] == "typing"

    def test_limit(self, capsys):
        main(argv=["search", "python", "--limit", "2", "--format", "json"])
        data = json.loads(capsys.readouterr().out)
        assert len(data) <= 2

    def test_limit_zero_rejected(self, capsys):
        with pytest.raises(SystemExit, match="2"):
            main(argv=["search", "typing", "--limit", "0"])

    def test_limit_negative_rejected(self, capsys):
        with pytest.raises(SystemExit, match="2"):
            main(argv=["search", "typing", "--limit", "-1"])

    def test_limit_over_max_rejected(self, capsys):
        with pytest.raises(SystemExit, match="2"):
            main(argv=["search", "typing", "--limit", "51"])

    def test_limit_non_integer_rejected(self, capsys):
        with pytest.raises(SystemExit, match="2"):
            main(argv=["search", "typing", "--limit", "abc"])

    def test_limit_float_rejected(self, capsys):
        with pytest.raises(SystemExit, match="2"):
            main(argv=["search", "typing", "--limit", "1.5"])

    def test_limit_boundary_1(self, capsys):
        main(argv=["search", "python", "--limit", "1", "--format", "json"])
        data = json.loads(capsys.readouterr().out)
        assert len(data) <= 1

    def test_limit_boundary_50(self, capsys):
        main(argv=["search", "python", "--limit", "50", "--format", "json"])
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)


class TestCmdRetrieve:
    def test_json_output(self, capsys):
        main(argv=["retrieve", "use-builtin-generics", "--format", "json"])
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert data[0]["id"] == "use-builtin-generics"

    def test_human_output(self, capsys):
        main(argv=["retrieve", "use-builtin-generics", "--format", "human"])
        out = capsys.readouterr().out
        assert "use-builtin-generics" in out
        assert "version match:" in out

    def test_comma_split_ids(self, capsys):
        main(argv=["retrieve", "use-builtin-generics,union-syntax", "--format", "json"])
        data = json.loads(capsys.readouterr().out)
        ids = {r["id"] for r in data}
        assert "use-builtin-generics" in ids
        assert "union-syntax" in ids

    def test_no_match_exits_1_json_envelope(self, capsys):
        with pytest.raises(SystemExit, match="1"):
            main(argv=["retrieve", "nonexistent-guide-id", "--format", "json"])
        data = json.loads(capsys.readouterr().out)
        assert "not_found" in data
        assert data["results"] == []
        assert data["not_found"][0]["id"] == "nonexistent-guide-id"

    def test_no_match_human_exits_1(self, capsys):
        with pytest.raises(SystemExit, match="1"):
            main(argv=["retrieve", "nonexistent-guide-id", "--format", "human"])
        assert "No guide found for" in capsys.readouterr().out

    def test_suggestion_human(self, capsys):
        with pytest.raises(SystemExit, match="1"):
            main(argv=["retrieve", "builtin-generics", "--format", "human"])
        out = capsys.readouterr().out
        assert "Did you mean" in out
        assert "use-builtin-generics" in out

    def test_suggestion_json(self, capsys):
        with pytest.raises(SystemExit, match="1"):
            main(argv=["retrieve", "builtin-generics", "--format", "json"])
        data = json.loads(capsys.readouterr().out)
        assert "use-builtin-generics" in data["not_found"][0]["suggestions"]

    def test_mixed_valid_and_invalid(self, capsys):
        with pytest.raises(SystemExit, match="1"):
            main(argv=["retrieve", "use-builtin-generics,zzz-fake", "--format", "json"])
        data = json.loads(capsys.readouterr().out)
        assert len(data["results"]) == 1
        assert data["results"][0]["id"] == "use-builtin-generics"
        assert data["not_found"][0]["id"] == "zzz-fake"

    def test_all_found_bare_list(self, capsys):
        main(argv=["retrieve", "use-builtin-generics", "--format", "json"])
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert data[0]["id"] == "use-builtin-generics"

    def test_trailing_comma_ignored(self, capsys):
        main(argv=["retrieve", "use-builtin-generics,", "--format", "json"])
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert data[0]["id"] == "use-builtin-generics"

    def test_all_commas_exits_1(self, capsys):
        with pytest.raises(SystemExit, match="1"):
            main(argv=["retrieve", ",,,", "--format", "human"])
        assert "No guide IDs provided" in capsys.readouterr().out

    def test_version_match_yes(self, capsys):
        main(
            argv=[
                "retrieve",
                "use-builtin-generics",
                "--python-version",
                "3.12",
                "--format",
                "human",
            ]
        )
        out = capsys.readouterr().out
        assert "YES" in out


class TestCmdList:
    def test_json_output(self, capsys):
        main(argv=["list", "--format", "json"])
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) >= 10

    def test_human_output(self, capsys):
        main(argv=["list", "--format", "human"])
        out = capsys.readouterr().out
        assert "layer" in out

    def test_category_filter(self, capsys):
        main(argv=["list", "--category", "stdlib", "--format", "json"])
        data = json.loads(capsys.readouterr().out)
        assert data
        for item in data:
            assert item["category"] == "stdlib"

    def test_version_filter(self, capsys):
        main(argv=["list", "--python-version", "3.11", "--format", "json"])
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_empty_exits_1(self, capsys):
        with pytest.raises(SystemExit, match="1"):
            main(argv=["list", "--category", "nonexistent_cat", "--format", "json"])

    def test_category_grouping_human(self, capsys):
        main(argv=["list", "--format", "human"])
        out = capsys.readouterr().out
        assert "[" in out and "]" in out


class TestCmdDetectVersion:
    def test_basic_output(self, capsys):
        main(argv=["detect-version"])
        out = capsys.readouterr().out.strip()
        assert out  # should return some version string


class TestCmdCheck:
    def test_json_output(self, tmp_path, capsys):
        p = tmp_path / "bad.py"
        p.write_text("from typing import List\n")
        with pytest.raises(SystemExit, match="1"):
            main(argv=["check", str(p), "--format", "json"])
        data = json.loads(capsys.readouterr().out)
        assert data["summary"]["total_matches"] >= 1

    def test_human_output(self, tmp_path, capsys):
        p = tmp_path / "bad.py"
        p.write_text("from typing import List\n")
        with pytest.raises(SystemExit, match="1"):
            main(argv=["check", str(p), "--format", "human"])
        assert "outdated pattern" in capsys.readouterr().out

    def test_clean_file(self, tmp_path, capsys):
        p = tmp_path / "clean.py"
        p.write_text("x: list[str] = []\n")
        main(argv=["check", str(p), "--format", "human"])
        assert "No outdated patterns" in capsys.readouterr().out

    def test_file_not_found(self, tmp_path, capsys):
        with pytest.raises(SystemExit, match="2"):
            main(argv=["check", str(tmp_path / "gone.py"), "--format", "json"])

    def test_quiet_suppresses_clean(self, tmp_path, capsys):
        p = tmp_path / "clean.py"
        p.write_text("x: list[str] = []\n")
        main(argv=["check", str(p), "--quiet", "--format", "human"])
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_exit_zero(self, tmp_path, capsys):
        p = tmp_path / "bad.py"
        p.write_text("from typing import List\n")
        main(argv=["check", str(p), "--exit-zero", "--format", "json"])
        data = json.loads(capsys.readouterr().out)
        assert data["summary"]["total_matches"] >= 1


class TestCmdHook:
    def test_bare_hook_exits_2(self, capsys):
        with pytest.raises(SystemExit, match="2"):
            main(argv=["hook"])
        assert "available hooks" in capsys.readouterr().err

    def test_unknown_hook_exits_2(self, capsys):
        with pytest.raises(SystemExit, match="2"):
            main(argv=["hook", "nonexistent"])
        assert "invalid choice" in capsys.readouterr().err

    def test_post_tool_use_py_match(self, tmp_path, capsys, monkeypatch):
        p = tmp_path / "bad.py"
        p.write_text("from typing import List\n")
        import io

        stdin_data = json.dumps({"tool_input": {"file_path": str(p)}})
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        with pytest.raises(SystemExit, match="2"):
            main(argv=["hook", "claude-post-tool-use"])
        assert "mpg:" in capsys.readouterr().err

    def test_post_tool_use_py_clean(self, tmp_path, monkeypatch):
        p = tmp_path / "clean.py"
        p.write_text("x: list[str] = []\n")
        import io

        stdin_data = json.dumps({"tool_input": {"file_path": str(p)}})
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        with pytest.raises(SystemExit, match="0"):
            main(argv=["hook", "claude-post-tool-use"])

    def test_post_tool_use_non_py(self, monkeypatch):
        import io

        stdin_data = json.dumps({"tool_input": {"file_path": "/tmp/x.js"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        with pytest.raises(SystemExit, match="0"):
            main(argv=["hook", "claude-post-tool-use"])

    def test_post_tool_use_malformed(self, monkeypatch):
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("{bad"))
        with pytest.raises(SystemExit, match="0"):
            main(argv=["hook", "claude-post-tool-use"])

    def test_post_tool_use_missing_keys(self, monkeypatch):
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"x": 1})))
        with pytest.raises(SystemExit, match="0"):
            main(argv=["hook", "claude-post-tool-use"])

    def test_post_tool_use_missing_file(self, monkeypatch):
        import io

        stdin_data = json.dumps({"tool_input": {"file_path": "/nonexistent/z.py"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        with pytest.raises(SystemExit, match="0"):
            main(argv=["hook", "claude-post-tool-use"])


class TestCmdSetupUninstall:
    def test_setup_dispatch(self):
        with patch("modern_python_guidance.setup_cmd.run_setup", return_value=0) as mock:
            with pytest.raises(SystemExit, match="0"):
                main(argv=["setup", "--dry-run"])
            mock.assert_called_once()
            call_kwargs = mock.call_args
            assert call_kwargs[1]["dry_run"] is True

    def test_uninstall_dispatch(self):
        with patch("modern_python_guidance.uninstall_cmd.run_uninstall", return_value=0) as mock:
            with pytest.raises(SystemExit, match="0"):
                main(argv=["uninstall", "--dry-run"])
            mock.assert_called_once()
            call_kwargs = mock.call_args
            assert call_kwargs[1]["dry_run"] is True

    def test_setup_nonzero_exit(self):
        with (
            patch("modern_python_guidance.setup_cmd.run_setup", return_value=1),
            pytest.raises(SystemExit, match="1"),
        ):
            main(argv=["setup", "--dry-run"])

    def test_uninstall_nonzero_exit(self):
        with (
            patch("modern_python_guidance.uninstall_cmd.run_uninstall", return_value=1),
            pytest.raises(SystemExit, match="1"),
        ):
            main(argv=["uninstall", "--dry-run"])


# --- helpers ---


def _make_ns(**kwargs):
    """Build a minimal argparse.Namespace for _resolve_format tests."""
    import argparse

    return argparse.Namespace(**kwargs)
