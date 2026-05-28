"""MCP server integration tests — subprocess-based stdio communication."""

from __future__ import annotations

import json
import subprocess
import sys

BIN = [sys.executable, "-m", "modern_python_guidance", "mcp"]


def _encode_message(msg: dict) -> bytes:
    return (json.dumps(msg) + "\n").encode("utf-8")


def _decode_messages(data: bytes) -> list[dict]:
    messages = []
    for line in data.decode("utf-8").splitlines():
        line = line.strip()
        if line:
            messages.append(json.loads(line))
    return messages


def _build_session(*requests: dict) -> bytes:
    return b"".join(_encode_message(r) for r in requests)


def _run_mcp(*requests: dict, timeout: int = 10) -> list[dict]:
    stdin_data = _build_session(*requests)
    proc = subprocess.run(
        BIN,
        input=stdin_data,
        capture_output=True,
        timeout=timeout,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr.decode()}"
    return _decode_messages(proc.stdout)


def _init_handshake() -> list[dict]:
    return [
        {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0.0.1"},
        }},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    ]


class TestInitialize:
    def test_initialize_returns_capabilities(self):
        responses = _run_mcp(*_init_handshake())
        assert len(responses) == 1
        result = responses[0]["result"]
        assert result["protocolVersion"] == "2024-11-05"
        assert "tools" in result["capabilities"]
        assert result["serverInfo"]["name"] == "modern-python-guidance"


class TestToolsList:
    def test_lists_four_tools(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        tools_response = responses[1]
        tools = tools_response["result"]["tools"]
        names = {t["name"] for t in tools}
        expected = {"search_guides", "retrieve_guides", "list_guides", "detect_python_version"}
        assert names == expected

    def test_schemas_have_required_fields(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        tools = responses[1]["result"]["tools"]
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"


class TestSearchGuides:
    def test_search_returns_results(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "search_guides",
                "arguments": {"query": "typing list"},
            }},
        )
        result = responses[1]["result"]
        assert "isError" not in result
        data = json.loads(result["content"][0]["text"])
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_search_enriched_keys(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "search_guides",
                "arguments": {"query": "pydantic validator"},
            }},
        )
        data = json.loads(responses[1]["result"]["content"][0]["text"])
        expected_keys = {
            "id", "title", "category", "layer", "tags", "python",
            "frequency", "score", "token_estimate", "fuzzy", "snippet",
        }
        assert set(data[0].keys()) == expected_keys
        assert isinstance(data[0]["tags"], list)
        assert isinstance(data[0]["python"], str)
        assert isinstance(data[0]["frequency"], str)
        assert isinstance(data[0]["snippet"], str)
        assert "→" in data[0]["snippet"]

    def test_search_empty_query(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "search_guides",
                "arguments": {"query": ""},
            }},
        )
        result = responses[1]["result"]
        assert result["isError"] is True

    def test_search_with_version_filter(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "search_guides",
                "arguments": {"query": "typing", "python_version": "3.12"},
            }},
        )
        result = responses[1]["result"]
        assert "isError" not in result

    def test_search_invalid_version_format(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "search_guides",
                "arguments": {"query": "typing", "python_version": "invalid"},
            }},
        )
        result = responses[1]["result"]
        assert result["isError"] is True

    def test_search_limit_clamped(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "search_guides",
                "arguments": {"query": "typing", "limit": 100},
            }},
        )
        result = responses[1]["result"]
        assert "isError" not in result
        data = json.loads(result["content"][0]["text"])
        assert len(data) <= 50


class TestRetrieveGuides:
    def test_retrieve_single_guide(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "retrieve_guides",
                "arguments": {"guide_ids": ["use-builtin-generics"]},
            }},
        )
        result = responses[1]["result"]
        assert "isError" not in result
        data = json.loads(result["content"][0]["text"])
        assert len(data) == 1
        assert data[0]["id"] == "use-builtin-generics"

    def test_retrieve_empty_ids(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "retrieve_guides",
                "arguments": {"guide_ids": []},
            }},
        )
        result = responses[1]["result"]
        assert result["isError"] is True

    def test_retrieve_nonexistent_id(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "retrieve_guides",
                "arguments": {"guide_ids": ["nonexistent-guide-xyz"]},
            }},
        )
        result = responses[1]["result"]
        assert "isError" not in result
        data = json.loads(result["content"][0]["text"])
        assert data == []


class TestListGuides:
    def test_list_all_guides(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "list_guides",
                "arguments": {},
            }},
        )
        result = responses[1]["result"]
        assert "isError" not in result
        data = json.loads(result["content"][0]["text"])
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_with_category_filter(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "list_guides",
                "arguments": {"category": "stdlib"},
            }},
        )
        result = responses[1]["result"]
        data = json.loads(result["content"][0]["text"])
        for guide in data:
            assert guide["category"] == "stdlib"


class TestDetectPythonVersion:
    def test_detect_version_default(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "detect_python_version",
                "arguments": {},
            }},
        )
        result = responses[1]["result"]
        assert "isError" not in result
        data = json.loads(result["content"][0]["text"])
        assert "python_version" in data

    def test_detect_version_rejects_absolute_path(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "detect_python_version",
                "arguments": {"project_dir": "/etc"},
            }},
        )
        result = responses[1]["result"]
        assert result["isError"] is True
        assert "/etc" not in result["content"][0]["text"]

    def test_detect_version_rejects_traversal(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "detect_python_version",
                "arguments": {"project_dir": "../../.."},
            }},
        )
        result = responses[1]["result"]
        assert result["isError"] is True


class TestProtocol:
    def test_unknown_method_returns_error(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "unknown/method", "params": {}},
        )
        error = responses[1].get("error")
        assert error is not None
        assert error["code"] == -32601

    def test_unknown_tool_returns_tool_error(self):
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "nonexistent_tool",
                "arguments": {},
            }},
        )
        result = responses[1]["result"]
        assert result["isError"] is True


class TestStdoutPollution:
    def test_no_non_jsonrpc_output(self):
        stdin_data = _build_session(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        proc = subprocess.run(BIN, input=stdin_data, capture_output=True, timeout=10)
        decoded = _decode_messages(proc.stdout)
        total_expected_bytes = sum(
            len((json.dumps(m) + "\n").encode()) for m in decoded
        )
        assert len(proc.stdout) == total_expected_bytes, (
            f"stdout contains {len(proc.stdout) - total_expected_bytes} extra bytes"
        )
