"""In-process unit tests for mcp_server.py — direct function calls for coverage."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

import modern_python_guidance.mcp_server as mcp


@pytest.fixture(autouse=True)
def _reset_index():
    """Reset the global singleton between tests."""
    mcp._index = None
    yield
    mcp._index = None


# --- Framing ---


class TestFraming:
    def test_read_message_eof(self):
        stream = io.StringIO("")
        assert mcp._read_message(stream) is None

    def test_read_message_valid_json(self):
        stream = io.StringIO('{"key": "value"}\n')
        result = mcp._read_message(stream)
        assert result == {"key": "value"}

    def test_read_message_skips_blank_lines(self):
        stream = io.StringIO('\n\n\n{"key": "value"}\n')
        result = mcp._read_message(stream)
        assert result == {"key": "value"}

    def test_read_message_many_blank_lines_no_recursion(self):
        lines = "\n" * 2000 + '{"ok": true}\n'
        stream = io.StringIO(lines)
        result = mcp._read_message(stream)
        assert result == {"ok": True}

    def test_read_message_blank_then_eof(self):
        stream = io.StringIO("\n\n\n")
        assert mcp._read_message(stream) is None

    def test_read_message_invalid_json_raises_skip(self):
        stream = io.StringIO("not-json\n")
        with pytest.raises(mcp._Skip, match="invalid JSON"):
            mcp._read_message(stream)

    def test_write_message(self):
        out = io.StringIO()
        mcp._write_message({"result": 42}, out)
        written = out.getvalue()
        assert json.loads(written.strip()) == {"result": 42}
        assert written.endswith("\n")


# --- Response builders ---


class TestResponseBuilders:
    def test_error_response(self):
        resp = mcp._error_response(1, -32600, "bad request")
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert resp["error"]["code"] == -32600
        assert resp["error"]["message"] == "bad request"

    def test_result_response(self):
        resp = mcp._result_response(2, {"data": "ok"})
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 2
        assert resp["result"] == {"data": "ok"}

    def test_tool_result_success(self):
        r = mcp._tool_result("hello")
        assert r["content"][0]["text"] == "hello"
        assert "isError" not in r

    def test_tool_result_error(self):
        r = mcp._tool_result("fail", is_error=True)
        assert r["content"][0]["text"] == "fail"
        assert r["isError"] is True


# --- _confine_path ---


class TestConfinePath:
    def test_none_returns_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = mcp._confine_path(None)
        assert result == tmp_path

    def test_valid_subdir(self, tmp_path, monkeypatch):
        sub = tmp_path / "sub"
        sub.mkdir()
        monkeypatch.chdir(tmp_path)
        result = mcp._confine_path("sub")
        assert isinstance(result, Path)
        assert result == sub

    def test_nonexistent_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = mcp._confine_path("does-not-exist")
        assert isinstance(result, str)
        assert "not found" in result

    def test_absolute_path_rejected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = mcp._confine_path("/etc")
        assert isinstance(result, str)
        assert "relative" in result

    def test_traversal_rejected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = mcp._confine_path("../../..")
        assert isinstance(result, str)

    def test_nested_traversal_rejected(self, tmp_path, monkeypatch):
        sub = tmp_path / "sub"
        sub.mkdir()
        monkeypatch.chdir(tmp_path)
        result = mcp._confine_path("sub/../../..")
        assert isinstance(result, str)

    def test_symlink_escape_rejected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        link = tmp_path / "escape"
        link.symlink_to("/tmp")
        result = mcp._confine_path("escape")
        assert isinstance(result, str)

    def test_cwd_is_root(self, monkeypatch):
        monkeypatch.chdir("/")
        result = mcp._confine_path(None)
        assert isinstance(result, str)
        assert "root" in result


# --- _validate_python_version ---


class TestValidateVersion:
    def test_none_is_valid(self):
        assert mcp._validate_python_version(None) is None

    def test_valid_version(self):
        assert mcp._validate_python_version("3.12") is None

    def test_invalid_version(self):
        err = mcp._validate_python_version("abc")
        assert err is not None
        assert "Invalid" in err

    def test_three_part_version(self):
        err = mcp._validate_python_version("3.12.1")
        assert err is not None


# --- Tool functions ---


class TestToolFunctions:
    def test_search_empty_query(self):
        r = mcp._tool_search({"query": ""})
        assert r["isError"] is True

    def test_search_valid(self):
        r = mcp._tool_search({"query": "typing"})
        data = json.loads(r["content"][0]["text"])
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_search_with_filters(self):
        r = mcp._tool_search(
            {
                "query": "typing",
                "python_version": "3.12",
                "category": "typing",
                "limit": 2,
            }
        )
        data = json.loads(r["content"][0]["text"])
        assert len(data) <= 2

    def test_search_invalid_version(self):
        r = mcp._tool_search({"query": "typing", "python_version": "bad"})
        assert r["isError"] is True

    def test_retrieve_empty_ids(self):
        r = mcp._tool_retrieve({"guide_ids": []})
        assert r["isError"] is True

    def test_retrieve_valid(self):
        r = mcp._tool_retrieve({"guide_ids": ["use-builtin-generics"]})
        data = json.loads(r["content"][0]["text"])
        assert isinstance(data, list)

    def test_retrieve_exactly_41_allowed(self):
        ids = [f"fake-{i}" for i in range(41)]
        r = mcp._tool_retrieve({"guide_ids": ids})
        assert r.get("isError") is not True

    def test_retrieve_42_rejected(self):
        ids = [f"fake-{i}" for i in range(42)]
        r = mcp._tool_retrieve({"guide_ids": ids})
        assert r["isError"] is True
        assert "41" in r["content"][0]["text"]

    def test_retrieve_invalid_version(self):
        r = mcp._tool_retrieve({"guide_ids": ["use-builtin-generics"], "python_version": "x"})
        assert r["isError"] is True

    def test_list_all(self):
        r = mcp._tool_list({})
        data = json.loads(r["content"][0]["text"])
        assert isinstance(data, list)
        assert len(data) >= 10

    def test_list_category_filter(self):
        r = mcp._tool_list({"category": "stdlib"})
        data = json.loads(r["content"][0]["text"])
        assert data
        for item in data:
            assert item["category"] == "stdlib"

    def test_list_version_filter(self):
        r = mcp._tool_list({"python_version": "3.11"})
        data = json.loads(r["content"][0]["text"])
        assert isinstance(data, list)
        assert data

    def test_list_invalid_version(self):
        r = mcp._tool_list({"python_version": "nope"})
        assert r["isError"] is True

    def test_detect_version_valid(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12"\n')
        r = mcp._tool_detect_version({"project_dir": None})
        data = json.loads(r["content"][0]["text"])
        assert "python_version" in data

    def test_detect_version_confined(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        r = mcp._tool_detect_version({"project_dir": "/etc"})
        assert r["isError"] is True


# --- _handle_tool_call ---


class TestHandleToolCall:
    def test_unknown_tool(self):
        r = mcp._handle_tool_call("nonexistent", {})
        assert r["isError"] is True
        assert "Unknown tool" in r["content"][0]["text"]

    def test_dispatch_search(self):
        r = mcp._handle_tool_call("search_guides", {"query": "typing"})
        assert "isError" not in r

    def test_exception_handling(self, monkeypatch):
        def boom(*_a, **_kw):
            raise RuntimeError("kaboom")

        monkeypatch.setattr(mcp, "_tool_search", boom)
        r = mcp._handle_tool_call("search_guides", {"query": "x"})
        assert r["isError"] is True
        assert "Internal error" in r["content"][0]["text"]


# --- _handle_request ---


class TestHandleRequest:
    def test_initialize(self):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        resp = mcp._handle_request(msg)
        assert resp is not None
        assert resp["id"] == 1
        assert "protocolVersion" in resp["result"]

    def test_initialize_notification_returns_none(self):
        msg = {"jsonrpc": "2.0", "method": "initialize", "params": {}}
        resp = mcp._handle_request(msg)
        assert resp is None

    def test_notifications_initialized(self):
        msg = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        assert mcp._handle_request(msg) is None

    def test_tools_list(self):
        msg = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        resp = mcp._handle_request(msg)
        assert resp is not None
        assert "tools" in resp["result"]
        assert len(resp["result"]["tools"]) == 4

    def test_tools_call(self):
        msg = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "search_guides", "arguments": {"query": "typing"}},
        }
        resp = mcp._handle_request(msg)
        assert resp is not None
        assert resp["id"] == 3

    def test_unknown_method(self):
        msg = {"jsonrpc": "2.0", "id": 4, "method": "nonexistent"}
        resp = mcp._handle_request(msg)
        assert resp is not None
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_unknown_notification_ignored(self):
        msg = {"jsonrpc": "2.0", "method": "custom/notification"}
        resp = mcp._handle_request(msg)
        assert resp is None

    def test_tools_call_notification_mode(self):
        msg = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "search_guides", "arguments": {"query": "typing"}},
        }
        resp = mcp._handle_request(msg)
        assert resp is None

    @pytest.mark.parametrize(
        "msg",
        [[1, 2, 3], "hello", 42, True],
        ids=["list", "string", "number", "bool"],
    )
    def test_non_dict_returns_invalid_request(self, msg):
        resp = mcp._handle_request(msg)
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] is None
        assert resp["error"]["code"] == -32600
        assert "expected JSON object" in resp["error"]["message"]


# --- serve ---


class TestServe:
    def test_empty_stdin_eof(self):
        sin = io.StringIO("")
        sout = io.StringIO()
        mcp.serve(stdin=sin, stdout=sout)
        assert sout.getvalue() == ""

    def test_single_request(self):
        req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        sin = io.StringIO(json.dumps(req) + "\n")
        sout = io.StringIO()
        mcp.serve(stdin=sin, stdout=sout)
        resp = json.loads(sout.getvalue().strip())
        assert resp["id"] == 1
        assert "protocolVersion" in resp["result"]

    def test_malformed_json_recovery(self):
        lines = (
            "not-valid-json\n"
            + json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            + "\n"
        )
        sin = io.StringIO(lines)
        sout = io.StringIO()
        mcp.serve(stdin=sin, stdout=sout)
        resp = json.loads(sout.getvalue().strip())
        assert resp["id"] == 1

    def test_multiple_requests(self):
        req1 = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        req2 = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        sin = io.StringIO(req1 + "\n" + req2 + "\n")
        sout = io.StringIO()
        mcp.serve(stdin=sin, stdout=sout)
        responses = [json.loads(line) for line in sout.getvalue().strip().split("\n")]
        assert len(responses) == 2
        assert responses[0]["id"] == 1
        assert responses[1]["id"] == 2

    def test_non_dict_json_recovery(self):
        lines = (
            json.dumps([1, 2, 3])
            + "\n"
            + json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            + "\n"
        )
        sin = io.StringIO(lines)
        sout = io.StringIO()
        mcp.serve(stdin=sin, stdout=sout)
        responses = [json.loads(line) for line in sout.getvalue().strip().split("\n")]
        assert len(responses) == 2
        assert responses[0]["error"]["code"] == -32600
        assert responses[0]["id"] is None
        assert responses[1]["id"] == 1
        assert "protocolVersion" in responses[1]["result"]
