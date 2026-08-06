"""End-to-end contract for dependency-aware guide applicability (#179)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CLI_BIN = [sys.executable, "-m", "modern_python_guidance"]
MCP_BIN = [*CLI_BIN, "mcp"]
_GUIDE_ID = "pydantic-v2-validators"
_SOURCE = "@validator('field')\ndef validate(value):\n    return value\n"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*CLI_BIN, *args], capture_output=True, text=True, timeout=10)


def _mcp_search(*, version: str | None) -> list[dict]:
    arguments: dict[str, object] = {
        "query": "pydantic validator",
        "limit": 50,
        "include_incompatible": True,
    }
    if version is not None:
        arguments["dependency_versions"] = {"package:pydantic": version}
    session = "\n".join(
        json.dumps(message)
        for message in (
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "search_guides", "arguments": arguments},
            },
        )
    )
    proc = subprocess.run(
        MCP_BIN, input=session + "\n", capture_output=True, text=True, timeout=10
    )
    assert proc.returncode == 0, proc.stderr
    response = json.loads(proc.stdout.splitlines()[-1])
    return json.loads(response["result"]["content"][0]["text"])


def _hook(file_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*CLI_BIN, "hook", "claude-post-tool-use"],
        input=json.dumps({"tool_input": {"file_path": str(file_path)}}),
        capture_output=True,
        text=True,
        timeout=10,
    )


def _write_project(root: Path, dependency: str | None) -> Path:
    dependencies = f'dependencies = ["pydantic=={dependency}"]\n' if dependency else ""
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "fixture"\nversion = "0"\n{dependencies}'
    )
    source = root / "model.py"
    source.write_text(_SOURCE)
    return source


def _guide_status(results: list[dict]) -> str:
    guide = next(item for item in results if item["id"] == _GUIDE_ID)
    return guide["dependency_compatibility"]["status"]


def test_pydantic_tri_state_is_consistent_across_cli_mcp_check_and_hook(tmp_path: Path) -> None:
    """V1 is suppressed, V2 is confirmed, and absence remains qualified."""
    cases = (("1.10.15", "incompatible"), ("2.7.4", "confirmed"), (None, "unknown"))
    for version, expected in cases:
        cli_args = [
            "search",
            "pydantic validator",
            "--dependency-version",
            f"package:pydantic={version}" if version else "package:other=1",
            "--include-incompatible",
            "--limit",
            "50",
            "--format",
            "json",
        ]
        cli = _run_cli(*cli_args)
        assert cli.returncode == 0
        assert _guide_status(json.loads(cli.stdout)) == expected
        assert _guide_status(_mcp_search(version=version)) == expected

        source = _write_project(tmp_path, version)
        checked = _run_cli(
            "check", str(source), "--project-dir", str(tmp_path), "--format", "json"
        )
        hooked = _hook(source)
        assert hooked.returncode == 0

        if expected == "incompatible":
            assert checked.returncode == 0
            assert _GUIDE_ID not in checked.stdout
            assert hooked.stdout == ""
        else:
            assert checked.returncode == 1
            match = next(
                item
                for item in json.loads(checked.stdout)["matches"]
                if item["guide_id"] == _GUIDE_ID
            )
            assert match["dependency_compatibility"]["status"] == expected
            context = json.loads(hooked.stdout)["hookSpecificOutput"]["additionalContext"]
            if expected == "confirmed":
                assert "apply the modern form" in context
            else:
                assert "dependency compatibility unknown; verify before applying" in context
