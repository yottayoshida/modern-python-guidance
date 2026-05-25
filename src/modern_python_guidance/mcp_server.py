"""MCP server — JSON-RPC 2.0 over stdio, zero external dependencies."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from modern_python_guidance import __version__
from modern_python_guidance.compat import VERSION_RE
from modern_python_guidance.guide_index import GuideIndex, build_index
from modern_python_guidance.retrieve import retrieve
from modern_python_guidance.search import search
from modern_python_guidance.version_detect import detect_version

log = logging.getLogger(__name__)

_index: GuideIndex | None = None


def _get_index() -> GuideIndex:
    global _index
    if _index is None:
        _index = build_index()
    return _index


# --- JSON-RPC framing (Content-Length, LSP-style) ---


def _read_message(stream: object = None) -> dict | None:
    buf = stream or sys.stdin.buffer
    headers: dict[str, str] = {}
    while True:
        line = buf.readline()
        if not line:
            return None
        line_str = line.decode("utf-8", errors="replace").rstrip("\r\n")
        if line_str == "":
            break
        if ":" in line_str:
            key, _, value = line_str.partition(":")
            headers[key.strip().lower()] = value.strip()

    length = int(headers.get("content-length", "0"))
    if length == 0:
        return None
    body = buf.read(length)
    return json.loads(body)


def _write_message(msg: dict, stream: object = None) -> None:
    out = stream or sys.stdout.buffer
    body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode()
    out.write(header)
    out.write(body)
    out.flush()


def _error_response(req_id: int | str | None, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _result_response(req_id: int | str | None, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _tool_result(text: str, *, is_error: bool = False) -> dict:
    result: dict = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["isError"] = True
    return result


# --- Tool schemas ---

TOOLS = [
    {
        "name": "search_guides",
        "description": (
            "Search modern Python pattern guides by keyword. Returns guide IDs, titles, "
            "scores, and token estimates. Use this to discover which guides exist before "
            "retrieving full content. Supports fuzzy matching when exact matches fail."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keywords (e.g. 'typing list', 'pydantic v2', 'httpx')",
                },
                "python_version": {
                    "type": "string",
                    "description": (
                        "Filter by Python version (e.g. '3.12'). "
                        "Only returns guides applicable to this version."
                    ),
                    "pattern": r"^\d+\.\d+$",
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category (e.g. 'stdlib', 'pydantic', 'fastapi')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (1-50, default: 10)",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "retrieve_guides",
        "description": (
            "Retrieve full content of one or more guides by ID. Returns the complete "
            "BAD/GOOD pattern with explanation, version compatibility, and token estimate. "
            "Call search_guides first to find guide IDs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "guide_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Guide IDs to retrieve (max 30)",
                    "maxItems": 30,
                },
                "python_version": {
                    "type": "string",
                    "description": "Target Python version for compatibility check (e.g. '3.12')",
                    "pattern": r"^\d+\.\d+$",
                },
            },
            "required": ["guide_ids"],
        },
    },
    {
        "name": "list_guides",
        "description": (
            "List all available guides with metadata. Returns IDs, titles, categories, "
            "layers, and Python version requirements. Use to browse the full catalog "
            "or filter by category/version."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter by category (e.g. 'stdlib', 'pydantic')",
                },
                "python_version": {
                    "type": "string",
                    "description": "Filter by Python version compatibility (e.g. '3.13')",
                    "pattern": r"^\d+\.\d+$",
                },
            },
        },
    },
    {
        "name": "detect_python_version",
        "description": (
            "Detect the target Python version for a project by reading pyproject.toml "
            "and .python-version. Returns a version string like '3.12'. Use this to "
            "determine which version to pass to search_guides and retrieve_guides."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_dir": {
                    "type": "string",
                    "description": (
                        "Relative path to project directory (relative to server CWD). "
                        "Defaults to current directory. Absolute paths are rejected."
                    ),
                },
            },
        },
    },
]


# --- CWD confinement ---


def _confine_path(project_dir_str: str | None) -> Path | str:
    """Validate project_dir stays within CWD. Returns Path on success, error string on failure."""
    cwd = Path.cwd()
    if cwd == Path("/"):
        return "Cannot detect version: server working directory is root"

    if project_dir_str is None:
        return cwd

    if Path(project_dir_str).is_absolute():
        return "project_dir must be a relative path"

    resolved = (cwd / project_dir_str).resolve()
    try:
        resolved.relative_to(cwd.resolve())
    except ValueError:
        return "project_dir must stay within the server working directory"

    if not resolved.is_dir():
        return "directory not found"

    return resolved


# --- Tool dispatch ---


def _handle_tool_call(name: str, arguments: dict) -> dict:
    try:
        if name == "search_guides":
            return _tool_search(arguments)
        if name == "retrieve_guides":
            return _tool_retrieve(arguments)
        if name == "list_guides":
            return _tool_list(arguments)
        if name == "detect_python_version":
            return _tool_detect_version(arguments)
        return _tool_result(f"Unknown tool: {name}", is_error=True)
    except Exception:
        log.exception("Tool execution error")
        return _tool_result("Internal error during tool execution", is_error=True)


def _validate_python_version(pv: str | None) -> str | None:
    if pv is not None and not VERSION_RE.match(pv):
        return f"Invalid python_version format: expected N.N (e.g. 3.12), got '{pv}'"
    return None


def _tool_search(arguments: dict) -> dict:
    query = arguments.get("query", "")
    if not query:
        return _tool_result("query is required", is_error=True)

    pv = arguments.get("python_version")
    err = _validate_python_version(pv)
    if err:
        return _tool_result(err, is_error=True)

    limit = max(1, min(50, arguments.get("limit", 10)))
    category = arguments.get("category")

    index = _get_index()
    results = search(index, query, python_version=pv, category=category, limit=limit)

    out = [
        {
            "id": r.guide_id,
            "title": r.meta.title,
            "category": r.meta.category,
            "layer": r.meta.layer,
            "score": r.score,
            "token_estimate": r.token_estimate,
            "fuzzy": r.fuzzy,
        }
        for r in results
    ]
    return _tool_result(json.dumps(out, indent=2, ensure_ascii=False))


def _tool_retrieve(arguments: dict) -> dict:
    guide_ids = arguments.get("guide_ids", [])
    if not guide_ids:
        return _tool_result("guide_ids is required and must not be empty", is_error=True)
    if len(guide_ids) > 30:
        return _tool_result("guide_ids exceeds maximum of 30", is_error=True)

    pv = arguments.get("python_version")
    err = _validate_python_version(pv)
    if err:
        return _tool_result(err, is_error=True)

    index = _get_index()
    results = retrieve(index, guide_ids, python_version=pv)
    return _tool_result(json.dumps(results, indent=2, ensure_ascii=False))


def _tool_list(arguments: dict) -> dict:
    pv = arguments.get("python_version")
    err = _validate_python_version(pv)
    if err:
        return _tool_result(err, is_error=True)

    category = arguments.get("category")
    index = _get_index()
    metas = index.all_meta()

    if category:
        metas = [m for m in metas if m.category == category]
    if pv:
        from modern_python_guidance.compat import version_compatible

        metas = [m for m in metas if version_compatible(m.python, pv)]

    metas.sort(key=lambda m: (m.layer, m.category, m.id))

    out = [
        {
            "id": m.id,
            "title": m.title,
            "category": m.category,
            "layer": m.layer,
            "python": m.python,
            "frequency": m.frequency,
        }
        for m in metas
    ]
    return _tool_result(json.dumps(out, indent=2, ensure_ascii=False))


def _tool_detect_version(arguments: dict) -> dict:
    project_dir_str = arguments.get("project_dir")
    result = _confine_path(project_dir_str)
    if isinstance(result, str):
        return _tool_result(result, is_error=True)

    version = detect_version(project_dir=result)
    return _tool_result(json.dumps({"python_version": version}))


# --- Server main loop ---

PROTOCOL_VERSION = "2024-11-05"


def _handle_request(msg: dict) -> dict | None:
    method = msg.get("method", "")
    req_id = msg.get("id")
    params = msg.get("params", {})

    if method == "initialize":
        return _result_response(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "modern-python-guidance", "version": __version__},
        })

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return _result_response(req_id, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        result = _handle_tool_call(tool_name, arguments)
        return _result_response(req_id, result)

    if req_id is not None:
        return _error_response(req_id, -32601, f"Method not found: {method}")

    return None


def serve(*, stdin: object = None, stdout: object = None) -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="%(message)s")

    while True:
        msg = _read_message(stdin)
        if msg is None:
            break

        response = _handle_request(msg)
        if response is not None:
            _write_message(response, stdout)


if __name__ == "__main__":
    serve()
