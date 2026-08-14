"""MCP server integration tests — subprocess-based stdio communication."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from conftest import design_md_field_paths, extract_design_md_keys, field_paths

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


def _assert_pure_jsonrpc_stream(data: bytes) -> list[dict]:
    """Assert stdout carries JSON-RPC messages and nothing else, then return them.

    Judged from the stream's *structure* alone — never by recomputing what the
    server "should" have written. An earlier version summed
    ``len(json.dumps(m) + "\\n")`` over the decoded messages and compared it to
    ``len(stdout)``; that recomputation defaults to ``ensure_ascii=True`` while
    the server serializes with ``ensure_ascii=False`` (``mcp_server.py``), so a
    single non-ASCII character anywhere in a tool description or tool result
    made the two byte counts diverge and failed the test with no stray output
    at all (#173). Recomputation also silently re-couples the test to
    ``indent``/``separators``, which are not part of what "no stray output"
    means.

    Deliberately does NOT reuse `_decode_messages`: that helper strips each
    line before parsing, which destroys the very evidence (blank lines,
    trailing whitespace) this check exists to find.

    Every violation raises AssertionError — including malformed JSON and
    invalid UTF-8, which would otherwise surface as JSONDecodeError /
    UnicodeDecodeError and make the falsification tests unable to pin a single
    failure type.

    The `jsonrpc` version marker alone is too weak an acceptance test: a stray
    `{"jsonrpc": "2.0", "debug": true}` line would carry it while being exactly
    the pollution this check exists to reject, so a response/notification body
    is required too. Callers should additionally assert the message count and
    ids they expect — a well-formed but *extra* message is still pollution, and
    only the caller knows how many belong there.
    """
    assert data, "stdout is empty; expected at least one JSON-RPC message"
    assert data.endswith(b"\n"), f"stdout does not end with a newline: {data[-40:]!r}"

    messages = []
    for i, raw in enumerate(data.split(b"\n")[:-1]):
        assert raw, f"stdout line {i} is blank; JSON-RPC framing allows no empty lines"
        assert raw == raw.strip(), f"stdout line {i} has leading/trailing whitespace: {raw!r}"
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise AssertionError(f"stdout line {i} is not valid JSON ({e}): {raw!r}") from e
        assert isinstance(msg, dict), f"stdout line {i} is not a JSON object: {raw!r}"
        assert msg.get("jsonrpc") == "2.0", f"stdout line {i} is not a JSON-RPC message: {raw!r}"
        assert {"result", "error", "method"} & msg.keys(), (
            f"stdout line {i} claims jsonrpc 2.0 but carries no result/error/method: {raw!r}"
        )
        messages.append(msg)
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
        {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0.0.1"},
            },
        },
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

    def test_duplicate_dependency_version_key_is_rejected_without_last_value_wins(self):
        raw_request = (
            b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":'
            b'{"name":"search_guides","arguments":{"query":"pydantic",'
            b'"dependency_versions":{"package:pydantic":"1.10.15",'
            b'"package:pydantic":"2.10.0"}}}}\n'
        )
        proc = subprocess.run(BIN, input=raw_request, capture_output=True, timeout=10)
        assert proc.returncode == 0
        assert proc.stdout == b""


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

    def test_search_guides_description_guide_count_matches_index(self):
        """#152 PR3: search_guides' description hardcodes a guide count
        ("41 guides") with no other test tying it to reality — unlike
        rules/modern-python.md (CI byte-matched against _build_rule_text)
        and SKILL.md (test_catalog_count_matches). Pin it to the actual
        index length so a future guide addition/removal can't leave this
        description silently stale."""
        from modern_python_guidance.guide_index import build_index

        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        tools = {t["name"]: t for t in responses[1]["result"]["tools"]}
        actual_count = len(build_index())
        assert f"{actual_count} guides" in tools["search_guides"]["description"]

    def test_search_guides_description_does_not_name_an_embedded_category(self):
        """#208: the description tells agents to search for patterns *outside*
        the ones the rules file already carries, and lists example categories.
        Naming a category that is now embedded sends the agent looking for
        guidance it was just handed — and this list went stale the moment
        pytest-parametrize moved into the rules body.

        Scoped to pytest rather than derived from the embedded set. Deriving
        it would mean sharing the embedded list between two test modules, and
        the general case has occurred once. When a second category moves in,
        that is the point to generalise.
        """
        responses = _run_mcp(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        tools = {t["name"]: t for t in responses[1]["result"]["tools"]}
        description = tools["search_guides"]["description"]
        marker = "already embedded in your project rules"
        assert marker in description, "the description no longer explains when to search"
        examples = description.split(marker, 1)[1].split(")", 1)[0]
        assert "pytest" not in examples, (
            "search_guides lists pytest as a reason to search, but pytest-parametrize"
            " is carried by the rules file"
        )


class TestSearchGuides:
    def test_search_returns_results(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_guides",
                    "arguments": {"query": "typing list"},
                },
            },
        )
        result = responses[1]["result"]
        assert "isError" not in result
        data = json.loads(result["content"][0]["text"])
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_search_enriched_keys(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_guides",
                    "arguments": {"query": "pydantic validator"},
                },
            },
        )
        data = json.loads(responses[1]["result"]["content"][0]["text"])
        assert extract_design_md_keys("search") <= set(data[0].keys())
        assert isinstance(data[0]["tags"], list)
        assert isinstance(data[0]["python"], str)
        assert isinstance(data[0]["frequency"], str)
        assert isinstance(data[0]["snippet"], str)
        assert "→" in data[0]["snippet"]

    def test_search_reports_detection_metadata(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_guides",
                    "arguments": {"query": "typing list"},
                },
            },
        )
        data = json.loads(responses[1]["result"]["content"][0]["text"])

        assert data[0]["detection"] == {
            "status": "detectable",
            "methods": ["regex", "ast-name"],
        }

    def test_search_empty_query(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_guides",
                    "arguments": {"query": ""},
                },
            },
        )
        result = responses[1]["result"]
        assert result["isError"] is True

    def test_search_with_version_filter(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_guides",
                    "arguments": {"query": "typing", "python_version": "3.12"},
                },
            },
        )
        result = responses[1]["result"]
        assert "isError" not in result

    def test_search_invalid_version_format(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_guides",
                    "arguments": {"query": "typing", "python_version": "invalid"},
                },
            },
        )
        result = responses[1]["result"]
        assert result["isError"] is True

    def test_search_limit_clamped(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_guides",
                    "arguments": {"query": "typing", "limit": 100},
                },
            },
        )
        result = responses[1]["result"]
        assert "isError" not in result
        data = json.loads(result["content"][0]["text"])
        assert len(data) <= 50


class TestTypeValidationSubprocess:
    def test_search_query_wrong_type(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_guides",
                    "arguments": {"query": 42},
                },
            },
        )
        result = responses[1]["result"]
        assert result["isError"] is True
        assert "query must be a string" in result["content"][0]["text"]

    def test_retrieve_guide_ids_string(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "retrieve_guides",
                    "arguments": {"guide_ids": "use-builtin-generics"},
                },
            },
        )
        result = responses[1]["result"]
        assert result["isError"] is True
        assert "guide_ids must be an array" in result["content"][0]["text"]


class TestRetrieveGuides:
    def test_retrieve_single_guide(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "retrieve_guides",
                    "arguments": {"guide_ids": ["use-builtin-generics"]},
                },
            },
        )
        result = responses[1]["result"]
        assert "isError" not in result
        data = json.loads(result["content"][0]["text"])
        assert len(data) == 1
        assert data[0]["id"] == "use-builtin-generics"

    def test_retrieve_empty_ids(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "retrieve_guides",
                    "arguments": {"guide_ids": []},
                },
            },
        )
        result = responses[1]["result"]
        assert result["isError"] is True

    def test_retrieve_nonexistent_id(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "retrieve_guides",
                    "arguments": {"guide_ids": ["nonexistent-guide-xyz"]},
                },
            },
        )
        result = responses[1]["result"]
        assert "isError" not in result
        data = json.loads(result["content"][0]["text"])
        assert "not_found" in data
        assert data["results"] == []
        assert data["not_found"][0]["id"] == "nonexistent-guide-xyz"


class TestListGuides:
    def test_list_all_guides(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "list_guides",
                    "arguments": {},
                },
            },
        )
        result = responses[1]["result"]
        assert "isError" not in result
        data = json.loads(result["content"][0]["text"])
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_stable_schema(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "list_guides",
                    "arguments": {},
                },
            },
        )
        data = json.loads(responses[1]["result"]["content"][0]["text"])
        assert extract_design_md_keys("list") <= set(data[0].keys())

    def test_list_reports_detection_metadata(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "list_guides",
                    "arguments": {},
                },
            },
        )
        data = {
            item["id"]: item for item in json.loads(responses[1]["result"]["content"][0]["text"])
        }

        assert data["use-builtin-generics"]["detection"] == {
            "status": "detectable",
            "methods": ["regex", "ast-name"],
        }
        assert data["dataclass-modern"]["detection"] == {
            "status": "advisory-only",
            "methods": [],
        }

    def test_list_with_category_filter(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "list_guides",
                    "arguments": {"category": "stdlib"},
                },
            },
        )
        result = responses[1]["result"]
        data = json.loads(result["content"][0]["text"])
        for guide in data:
            assert guide["category"] == "stdlib"


class TestDetectPythonVersion:
    def test_detect_version_default(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "detect_python_version",
                    "arguments": {},
                },
            },
        )
        result = responses[1]["result"]
        assert "isError" not in result
        data = json.loads(result["content"][0]["text"])
        assert "python_version" in data

    def test_detect_version_matches_the_documented_field_paths(self):
        """The MCP payload against the same section the CLI is held to.

        `_tool_detect_version` builds its own dict rather than calling the CLI
        serializer, so the two can drift apart while each looks right on its
        own. design.md documents one shape for both; this is the MCP half of
        holding them to it.
        """
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "detect_python_version", "arguments": {}},
            },
        )
        data = json.loads(responses[1]["result"]["content"][0]["text"])
        assert field_paths(data) == design_md_field_paths("detect-version")

    def test_detect_version_rejects_absolute_path(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "detect_python_version",
                    "arguments": {"project_dir": "/etc"},
                },
            },
        )
        result = responses[1]["result"]
        assert result["isError"] is True
        assert "/etc" not in result["content"][0]["text"]

    def test_detect_version_rejects_traversal(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "detect_python_version",
                    "arguments": {"project_dir": "../../.."},
                },
            },
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
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "nonexistent_tool",
                    "arguments": {},
                },
            },
        )
        result = responses[1]["result"]
        assert result["isError"] is True


class TestMalformedParams:
    def test_non_dict_params_returns_error_and_server_continues(self):
        responses = _run_mcp(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": "bad"},
            {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}},
        )
        assert len(responses) == 2
        assert responses[0]["error"]["code"] == -32602
        assert responses[0]["id"] == 1
        assert "expected object" in responses[0]["error"]["message"]
        assert "protocolVersion" in responses[1]["result"]

    def test_non_dict_arguments_returns_error_and_server_continues(self):
        responses = _run_mcp(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "search_guides", "arguments": "not-a-dict"},
            },
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        error = responses[1].get("error")
        assert error is not None
        assert error["code"] == -32602
        assert "expected object" in error["message"]
        assert responses[2]["id"] == 2
        assert "tools" in responses[2]["result"]


class TestStdoutPollution:
    def test_no_non_jsonrpc_output(self):
        stdin_data = _build_session(
            *_init_handshake(),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        proc = subprocess.run(BIN, input=stdin_data, capture_output=True, timeout=10)
        assert proc.returncode == 0, f"stderr: {proc.stderr.decode()}"
        messages = _assert_pure_jsonrpc_stream(proc.stdout)
        # Per-line structure alone cannot catch a well-formed but *extra*
        # message, so pin exactly which responses belong on stdout: one for
        # `initialize` and one for `tools/list`. `notifications/initialized`
        # is a notification and must produce no output at all.
        assert [m["id"] for m in messages] == [0, 1], f"unexpected responses: {messages}"

    def test_tool_call_response_with_non_ascii_is_not_pollution(self):
        """#173 in its live form: `guide_index` composes BAD/GOOD summaries with
        a `→`, so a real `search_guides` response carries raw UTF-8 on stdout.
        Under the old byte-count comparison this response measured 12 bytes
        "short" and would have failed; the test only stayed green because it
        exercised `tools/list` alone. Pinned here so the fix is exercised
        against the server's own output, not just synthetic bytes.
        """
        stdin_data = _build_session(
            *_init_handshake(),
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "search_guides",
                    "arguments": {"query": "pydantic validator"},
                },
            },
        )
        proc = subprocess.run(BIN, input=stdin_data, capture_output=True, timeout=10)
        assert proc.returncode == 0, f"stderr: {proc.stderr.decode()}"
        assert any(b >= 0x80 for b in proc.stdout), (
            "no non-ASCII byte on stdout; this test no longer exercises the #173 path"
        )
        messages = _assert_pure_jsonrpc_stream(proc.stdout)
        assert [m["id"] for m in messages] == [0, 1], f"unexpected responses: {messages}"


class TestStdoutPurityChecker:
    """Falsify `_assert_pure_jsonrpc_stream` itself (#173).

    `TestStdoutPollution` only ever sees a clean server, so on its own it
    cannot distinguish "the server is clean" from "the checker accepts
    anything". These tests pin both directions: every pollution shape the
    previous byte-count comparison caught must still fail, and a non-ASCII
    payload — the false positive that motivated #173 — must pass.
    """

    @staticmethod
    def _clean_line() -> str:
        return json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}})

    def test_rejects_stray_non_json_line(self):
        data = b"DEBUG: writing index\n" + (self._clean_line() + "\n").encode()
        with pytest.raises(AssertionError, match="not valid JSON"):
            _assert_pure_jsonrpc_stream(data)

    def test_rejects_blank_line(self):
        data = (self._clean_line() + "\n").encode() + b"\n"
        with pytest.raises(AssertionError, match="blank"):
            _assert_pure_jsonrpc_stream(data)

    def test_rejects_trailing_whitespace(self):
        data = (self._clean_line() + "  \n").encode()
        with pytest.raises(AssertionError, match="whitespace"):
            _assert_pure_jsonrpc_stream(data)

    def test_rejects_missing_final_newline(self):
        data = self._clean_line().encode()
        with pytest.raises(AssertionError, match="newline"):
            _assert_pure_jsonrpc_stream(data)

    def test_rejects_valid_json_that_is_not_jsonrpc(self):
        data = (json.dumps({"result": "no jsonrpc key"}) + "\n").encode()
        with pytest.raises(AssertionError, match="not a JSON-RPC message"):
            _assert_pure_jsonrpc_stream(data)

    def test_rejects_jsonrpc_marker_without_a_message_body(self):
        """A stray line can carry `"jsonrpc": "2.0"` and still be pollution;
        the version marker alone is not an acceptance test."""
        data = (self._clean_line() + "\n").encode() + b'{"jsonrpc": "2.0", "debug": true}\n'
        with pytest.raises(AssertionError, match="no result/error/method"):
            _assert_pure_jsonrpc_stream(data)

    def test_rejects_invalid_utf8_as_assertion_error(self):
        """Malformed bytes must fail the same way everything else does, so the
        falsification tests can pin one failure type."""
        data = b'{"jsonrpc": "2.0", "id": 1, "result": "\xff\xfe"}\n'
        with pytest.raises(AssertionError, match="not valid JSON"):
            _assert_pure_jsonrpc_stream(data)

    def test_accepts_a_notification_without_id(self):
        """Guard against over-tightening: a server-initiated notification has
        `method` and no `id`/`result`, and must not be read as pollution."""
        data = (json.dumps({"jsonrpc": "2.0", "method": "notifications/x"}) + "\n").encode()
        assert len(_assert_pure_jsonrpc_stream(data)) == 1

    def test_accepts_non_ascii_payload(self):
        """The #173 regression: the server writes with `ensure_ascii=False`, so
        raw UTF-8 reaches stdout. That is not pollution and must stay green."""
        msg = {"jsonrpc": "2.0", "id": 1, "result": {"text": "guides — 41 total"}}
        data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        # Guard against a vacuous fixture: with the default `ensure_ascii=True`
        # the em dash is escaped to a pure-ASCII \\uXXXX sequence, and this test
        # would assert nothing about non-ASCII handling while still passing.
        assert any(b >= 0x80 for b in data), "fixture escaped to ASCII; test would be vacuous"
        decoded = _assert_pure_jsonrpc_stream(data)
        assert decoded[0]["result"]["text"] == "guides — 41 total"
