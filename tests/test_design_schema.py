"""Pin docs/design.md JSON schema examples to live serializer output.

design.md documents the JSON shapes returned by the CLI/MCP serializers. These
tests parse the documented examples and compare their key sets against the live
output of the corresponding commands, so the docs cannot silently drift from the
serializers in either direction.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

DESIGN_MD = Path(__file__).resolve().parent.parent / "docs" / "design.md"

BIN = [sys.executable, "-m", "modern_python_guidance"]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*BIN, *args],
        capture_output=True,
        text=True,
        timeout=10,
    )


def _json_blocks_under_heading(text: str, heading: str) -> list[str]:
    """Return the ```json blocks that appear under ``heading`` (a ### section).

    The section runs from ``heading`` up to the next ``##``-or-deeper heading.
    """
    heading_pat = re.compile(rf"^{re.escape(heading)}\s*$", re.MULTILINE)
    m = heading_pat.search(text)
    assert m is not None, f"heading not found in design.md: {heading!r}"
    start = m.end()
    next_heading = re.compile(r"^##", re.MULTILINE).search(text, start)
    end = next_heading.start() if next_heading else len(text)
    section = text[start:end]
    return re.findall(r"```json\n(.*?)```", section, re.DOTALL)


def _strip_placeholder_keys(keys: set[str]) -> set[str]:
    """Drop documentation placeholder keys (e.g. the ``"..."`` elision marker)."""
    return {k for k in keys if k != "..."}


class TestDesignDocSchemaContract:
    """Pin docs/design.md JSON schema examples to live serializer output."""

    def test_search_schema_keys(self):
        text = DESIGN_MD.read_text()
        blocks = _json_blocks_under_heading(text, "### JSON schema (search)")
        assert len(blocks) == 1
        doc_keys = set(json.loads(blocks[0])[0].keys())

        r = run_cli("search", "pydantic", "--format", "json")
        assert r.returncode == 0
        live_keys = set(json.loads(r.stdout)[0].keys())

        assert doc_keys == live_keys

    def test_retrieve_schema_keys(self):
        text = DESIGN_MD.read_text()
        blocks = _json_blocks_under_heading(text, "### JSON schema (retrieve)")
        # First block: found-array shape. Second block: not_found envelope.
        assert len(blocks) == 2
        doc_keys = set(json.loads(blocks[0])[0].keys())

        r = run_cli("retrieve", "use-builtin-generics", "--format", "json")
        assert r.returncode == 0
        live_keys = set(json.loads(r.stdout)[0].keys())

        assert doc_keys == live_keys

    def test_list_schema_keys(self):
        text = DESIGN_MD.read_text()
        blocks = _json_blocks_under_heading(text, "### JSON schema (list)")
        assert len(blocks) == 1
        doc_keys = set(json.loads(blocks[0])[0].keys())

        r = run_cli("list", "--format", "json")
        assert r.returncode == 0
        live_keys = set(json.loads(r.stdout)[0].keys())

        assert doc_keys == live_keys

    def test_not_found_envelope_keys(self):
        text = DESIGN_MD.read_text()
        blocks = _json_blocks_under_heading(text, "### JSON schema (retrieve)")
        assert len(blocks) == 2
        envelope = json.loads(blocks[1])
        doc_top_keys = set(envelope.keys())
        doc_results_keys = _strip_placeholder_keys(set(envelope["results"][0].keys()))
        doc_not_found_keys = set(envelope["not_found"][0].keys())

        r = run_cli(
            "retrieve",
            "use-builtin-generics,no-such-guide",
            "--format",
            "json",
        )
        # CLI exits 1 when any requested ID is missing.
        assert r.returncode == 1
        live = json.loads(r.stdout)
        live_top_keys = set(live.keys())
        live_results_keys = set(live["results"][0].keys())
        live_not_found_keys = set(live["not_found"][0].keys())

        assert doc_top_keys == live_top_keys == {"results", "not_found"}
        # The documented results[0] is a placeholder; live results reuse the
        # found-guide shape, which test_retrieve_schema_keys pins separately.
        assert doc_results_keys == set()
        assert live_results_keys
        assert doc_not_found_keys == live_not_found_keys == {"id", "suggestions"}
