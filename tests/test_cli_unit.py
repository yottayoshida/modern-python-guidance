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


class TestCmdHookVersionDetection:
    """#117: the hook resolves the project's target Python version from the edited file."""

    UNION_BAD = (
        "from typing import Optional\n\ndef f(x: Optional[int]) -> Optional[int]:\n    return x\n"
    )

    def _run_hook(self, monkeypatch, file_path):
        import io

        stdin_data = json.dumps({"tool_input": {"file_path": str(file_path)}})
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
        main(argv=["hook", "claude-post-tool-use"])

    def test_py38_project_suppresses_310_patterns(self, tmp_path, capsys, monkeypatch):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nrequires-python = ">=3.8"\n'
        )
        p = tmp_path / "bad.py"
        p.write_text(self.UNION_BAD)
        with pytest.raises(SystemExit, match="0"):
            self._run_hook(monkeypatch, p)
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out == ""

    def test_py310_project_flags_union_syntax(self, tmp_path, capsys, monkeypatch):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nrequires-python = ">=3.10"\n'
        )
        p = tmp_path / "bad.py"
        p.write_text(self.UNION_BAD)
        with pytest.raises(SystemExit, match="2"):
            self._run_hook(monkeypatch, p)
        err = capsys.readouterr().err
        assert "union-syntax" in err
        assert "[target: py3.10]" in err

    def test_no_config_defaults_to_311(self, tmp_path, capsys, monkeypatch):
        """Spec (plan #117): no usable config anywhere -> filter on DEFAULT_VERSION 3.11."""
        p = tmp_path / "bad.py"
        p.write_text(self.UNION_BAD)
        with pytest.raises(SystemExit, match="2"):
            self._run_hook(monkeypatch, p)
        assert "[target: py3.11]" in capsys.readouterr().err

    def test_malformed_pyproject_clean_file_silent(self, tmp_path, capsys, monkeypatch):
        (tmp_path / "pyproject.toml").write_text("this is [not valid toml")
        p = tmp_path / "clean.py"
        p.write_text("x: list[str] = []\n")
        with pytest.raises(SystemExit, match="0"):
            self._run_hook(monkeypatch, p)
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out == ""

    @pytest.mark.parametrize(
        "pyproject_content",
        [
            'project = "not-a-table"\n',
            'tool = "not-a-table"\n',
            '[tool.poetry]\ndependencies = "not-a-table"\n',
            "[project]\nrequires-python = 3.8\n",
        ],
        ids=["project-not-table", "tool-not-table", "deps-not-table", "requires-python-float"],
    )
    def test_schema_invalid_pyproject_clean_file_silent(
        self, tmp_path, capsys, monkeypatch, pyproject_content
    ):
        """Valid TOML violating the pyproject schema must not break the hook contract."""
        (tmp_path / "pyproject.toml").write_text(pyproject_content)
        p = tmp_path / "clean.py"
        p.write_text("x: list[str] = []\n")
        with pytest.raises(SystemExit, match="0"):
            self._run_hook(monkeypatch, p)
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out == ""

    def test_monorepo_nearest_usable_config_wins(self, tmp_path, capsys, monkeypatch):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "root"\nrequires-python = ">=3.8"\n'
        )
        sub = tmp_path / "services" / "api"
        sub.mkdir(parents=True)
        # Nearest pyproject has no version info; the walk must continue upward.
        (sub / "pyproject.toml").write_text('[tool.other]\nkey = "v"\n')
        p = sub / "bad.py"
        p.write_text(self.UNION_BAD)
        with pytest.raises(SystemExit, match="0"):
            self._run_hook(monkeypatch, p)
        assert capsys.readouterr().err == ""

    def test_python_version_file_detected(self, tmp_path, capsys, monkeypatch):
        (tmp_path / ".python-version").write_text("3.9\n")
        p = tmp_path / "bad.py"
        p.write_text(self.UNION_BAD)
        with pytest.raises(SystemExit, match="0"):
            self._run_hook(monkeypatch, p)
        assert capsys.readouterr().err == ""

    def test_relative_file_path_resolved(self, tmp_path, capsys, monkeypatch):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nrequires-python = ">=3.8"\n'
        )
        p = tmp_path / "bad.py"
        p.write_text(self.UNION_BAD)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit, match="0"):
            self._run_hook(monkeypatch, "bad.py")
        assert capsys.readouterr().err == ""

    def test_nearest_usable_config_wins_over_parent(self, tmp_path, capsys, monkeypatch):
        """Positive observation: the child's 3.10 beats the parent's 3.8."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "root"\nrequires-python = ">=3.8"\n'
        )
        sub = tmp_path / "svc"
        sub.mkdir()
        (sub / "pyproject.toml").write_text(
            '[project]\nname = "svc"\nrequires-python = ">=3.10"\n'
        )
        p = sub / "bad.py"
        p.write_text(self.UNION_BAD)
        with pytest.raises(SystemExit, match="2"):
            self._run_hook(monkeypatch, p)
        assert "[target: py3.10]" in capsys.readouterr().err

    def test_malformed_child_falls_back_to_parent_config(self, tmp_path, capsys, monkeypatch):
        """Positive observation: the parent's 3.8 suppresses union-syntax, proving
        the broken child config was skipped (not just a clean-silence artifact)."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "root"\nrequires-python = ">=3.8"\n'
        )
        sub = tmp_path / "svc"
        sub.mkdir()
        (sub / "pyproject.toml").write_text("not [valid toml")
        p = sub / "bad.py"
        p.write_text(self.UNION_BAD)
        with pytest.raises(SystemExit, match="0"):
            self._run_hook(monkeypatch, p)
        assert capsys.readouterr().err == ""

    def test_config_at_walk_depth_limit_detected(self, tmp_path, capsys, monkeypatch):
        """Config exactly at depth 40 from the edited file is still found."""
        from modern_python_guidance.version_detect import _MAX_WALK_DEPTH

        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nrequires-python = ">=3.8"\n'
        )
        nested = tmp_path
        for i in range(_MAX_WALK_DEPTH):
            nested = nested / f"d{i}"
        nested.mkdir(parents=True)
        p = nested / "bad.py"
        p.write_text(self.UNION_BAD)
        with pytest.raises(SystemExit, match="0"):
            self._run_hook(monkeypatch, p)
        assert capsys.readouterr().err == ""

    def test_config_beyond_walk_depth_limit_ignored(self, tmp_path, capsys, monkeypatch):
        """Config at depth 41 is out of reach -> default 3.11 -> union-syntax flagged."""
        from modern_python_guidance.version_detect import _MAX_WALK_DEPTH

        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nrequires-python = ">=3.8"\n'
        )
        nested = tmp_path
        for i in range(_MAX_WALK_DEPTH + 1):
            nested = nested / f"d{i}"
        nested.mkdir(parents=True)
        p = nested / "bad.py"
        p.write_text(self.UNION_BAD)
        with pytest.raises(SystemExit, match="2"):
            self._run_hook(monkeypatch, p)
        assert "[target: py3.11]" in capsys.readouterr().err

    def test_logger_level_restored_after_hook(self, tmp_path, monkeypatch):
        """The hook-wide logger silencing is restored even across sys.exit."""
        import logging

        pkg_logger = logging.getLogger("modern_python_guidance")
        original = pkg_logger.level
        pkg_logger.setLevel(logging.DEBUG)
        try:
            p = tmp_path / "clean.py"
            p.write_text("x = 1\n")
            with pytest.raises(SystemExit, match="0"):
                self._run_hook(monkeypatch, p)
            assert pkg_logger.level == logging.DEBUG
        finally:
            pkg_logger.setLevel(original)

    def test_detection_error_falls_back_and_restores_logger(self, tmp_path, capsys, monkeypatch):
        """A raising detector must not crash the hook (fail-safe to default),
        and the hook-wide logger silencing is restored afterwards."""
        import logging

        from modern_python_guidance import version_detect

        def boom(_dir):
            raise RuntimeError("detection blew up")

        pkg_logger = logging.getLogger("modern_python_guidance")
        original = pkg_logger.level
        pkg_logger.setLevel(logging.DEBUG)
        monkeypatch.setattr(version_detect, "detect_configured_version", boom)
        try:
            p = tmp_path / "clean.py"
            p.write_text("x = 1\n")
            with pytest.raises(SystemExit, match="0"):
                self._run_hook(monkeypatch, p)
            assert capsys.readouterr().err == ""
            assert pkg_logger.level == logging.DEBUG
        finally:
            pkg_logger.setLevel(original)

    def test_undecodable_config_clean_file_silent(self, tmp_path, capsys, monkeypatch):
        """Non-UTF-8 config bytes anywhere on the walk must not crash the hook."""
        (tmp_path / "pyproject.toml").write_bytes(b"\xff\xfe\x00b\x00r\x00o\x00k")
        p = tmp_path / "clean.py"
        p.write_text("x: list[str] = []\n")
        with pytest.raises(SystemExit, match="0"):
            self._run_hook(monkeypatch, p)
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out == ""

    def test_recursion_bomb_pyproject_clean_file_silent(self, tmp_path, capsys, monkeypatch):
        """Deeply nested TOML (RecursionError in tomllib, under the size cap)
        must not crash the hook."""
        (tmp_path / "pyproject.toml").write_text("a = " + "[" * 10000 + "]" * 10000)
        p = tmp_path / "clean.py"
        p.write_text("x: list[str] = []\n")
        with pytest.raises(SystemExit, match="0"):
            self._run_hook(monkeypatch, p)
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out == ""


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
