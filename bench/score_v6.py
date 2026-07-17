#!/usr/bin/env python3
"""V6 reach-benchmark scorer.

Parses --output-format stream-json transcripts (one per chained turn) plus
the optional hook-shim log, and reports whether the mpg guide catalog was
ever actually referenced during an organic multi-turn .py-editing session --
via a real MCP tool_use call or a real `mpg retrieve/search/check/list` CLI
invocation inside a Bash tool_use -- not via grep-over-final-text, which is
a known false positive/negative risk for this metric (a session can discuss
mpg without calling it, or call it without the word appearing in the final
reply).

Usage:
    python3 bench/score_v6.py <run_suffix>              # e.g. 1-1-v6-guidance-with-hook
    python3 bench/score_v6.py --aggregate <run_id>       # e.g. 1 -> all v6 runs under run_id 1
    python3 bench/score_v6.py <run_suffix> --format json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_DIR / "results"

# Only these actually reach the guide catalog. `mcp__mpg__detect_python_version`
# is deliberately excluded -- it only reports the project's Python version and
# never touches guide content, so calling it alone must not count as a reach.
MCP_REACH_TOOLS = frozenset(
    {"mcp__mpg__list_guides", "mcp__mpg__retrieve_guides", "mcp__mpg__search_guides"}
)

# Matches a real `mpg`/`python -m modern_python_guidance` CLI invocation of
# one of the catalog subcommands, anchored at the start of the command or
# after a shell separator (;, &&, ||, |) so it isn't fooled by the token
# appearing inside an unrelated argument or path.
CLI_INVOCATION_RE = re.compile(
    r"(?:^|[;&|]\s*)(?:\S*/)?"
    r"(?:mpg|python3?\s+-m\s+modern_python_guidance)\s+(retrieve|search|check|list)\b"
)

CONDITION_RE = re.compile(r"v6-(baseline|guidance-no-hook|guidance-with-hook)$")


@dataclass
class SessionReach:
    condition: str
    run_suffix: str
    py_edit_count: int = 0
    mcp_calls: list[str] = field(default_factory=list)
    cli_calls: list[str] = field(default_factory=list)
    hook_firings: int = 0
    hook_firings_with_context: int = 0
    turns_parsed: int = 0
    parse_warnings: list[str] = field(default_factory=list)

    @property
    def reached(self) -> bool:
        return bool(self.mcp_calls or self.cli_calls)


def _iter_jsonl(path: Path):
    """Stream a JSONL file one line at a time (not read_text().splitlines(),
    which would hold the whole file plus a full line list in memory at
    once -- transcripts run to 100s of KB)."""
    with path.open(encoding="utf-8", errors="replace") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                continue


def _scan_transcript(path: Path, reach: SessionReach, seen_tool_use_ids: set[str]) -> None:
    """Scan one turn's transcript, deduping tool_use blocks by id against
    `seen_tool_use_ids` (shared across all turns of the session). A
    `--resume`d turn's stream-json can re-emit prior-turn messages verbatim;
    without this, a multi-turn session would double-count edits/calls that
    only happened once.
    """
    reach.turns_parsed += 1
    tool_results: dict[str, bool] = {}  # tool_use_id -> is_error
    pending_cli_calls: list[tuple[str, str]] = []  # (tool_use_id, subcommand)

    for obj in _iter_jsonl(path):
        message = obj.get("message") if isinstance(obj, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")

            if block_type == "tool_result":
                tool_use_id = block.get("tool_use_id")
                if isinstance(tool_use_id, str):
                    tool_results[tool_use_id] = bool(block.get("is_error"))
                continue

            if block_type != "tool_use":
                continue

            tool_use_id = block.get("id")
            if isinstance(tool_use_id, str):
                if tool_use_id in seen_tool_use_ids:
                    continue
                seen_tool_use_ids.add(tool_use_id)

            name = block.get("name", "")
            raw_input = block.get("input")
            tool_input = raw_input if isinstance(raw_input, dict) else {}

            if name in MCP_REACH_TOOLS:
                reach.mcp_calls.append(name)
                continue

            if name == "Bash":
                command = tool_input.get("command", "")
                if isinstance(command, str) and isinstance(tool_use_id, str):
                    m = CLI_INVOCATION_RE.search(command)
                    if m:
                        pending_cli_calls.append((tool_use_id, m.group(1)))
                continue

            if name in ("Edit", "Write"):
                file_path = tool_input.get("file_path", "")
                if isinstance(file_path, str) and file_path.endswith(".py"):
                    reach.py_edit_count += 1

    # A Bash invocation that matched the CLI pattern only counts as a real
    # reach if it didn't error out -- e.g. `mpg` isn't on PATH inside the
    # isolated tmpdir unless a session explicitly installed it, so a typed
    # `mpg retrieve ...` attempt commonly fails with "command not found".
    # Missing tool_result (schema uncertainty) defaults to counting it,
    # since the failure case is the one we know we must not miscount.
    for tool_use_id, subcommand in pending_cli_calls:
        if not tool_results.get(tool_use_id):
            reach.cli_calls.append(subcommand)


def _scan_hook_log(path: Path, reach: SessionReach) -> None:
    if not path.exists():
        return
    for entry in _iter_jsonl(path):
        reach.hook_firings += 1
        if entry.get("additional_context_present"):
            reach.hook_firings_with_context += 1


def score_run(run_suffix: str) -> SessionReach:
    results_dir = RESULTS_DIR / f"run-{run_suffix}"
    if not results_dir.is_dir():
        print(f"ERROR: results dir not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    condition_match = CONDITION_RE.search(run_suffix)
    condition = condition_match.group(1) if condition_match else "unknown"

    reach = SessionReach(condition=condition, run_suffix=run_suffix)

    turn_files = sorted(results_dir.glob("turn-*.stream.jsonl"))
    if not turn_files:
        reach.parse_warnings.append("no turn-*.stream.jsonl files found")
    seen_tool_use_ids: set[str] = set()
    for turn_file in turn_files:
        _scan_transcript(turn_file, reach, seen_tool_use_ids)

    _scan_hook_log(results_dir / "hook-shim.log", reach)

    return reach


def _print_human(reach: SessionReach) -> None:
    print(f"=== V6 Reach: {reach.run_suffix} ===")
    print(f"Condition:            {reach.condition}")
    print(f"Turns parsed:         {reach.turns_parsed}")
    print(f".py Edit/Write count: {reach.py_edit_count}")
    print(f"MCP catalog calls:    {len(reach.mcp_calls)} {reach.mcp_calls or ''}")
    print(f"CLI catalog calls:    {len(reach.cli_calls)} {reach.cli_calls or ''}")
    with_ctx = reach.hook_firings_with_context
    print(f"Hook firings:         {reach.hook_firings} (with context: {with_ctx})")
    print(f"Reached catalog:      {'YES' if reach.reached else 'no'}")
    if reach.parse_warnings:
        print(f"Warnings:             {'; '.join(reach.parse_warnings)}")


def _print_json(reach: SessionReach) -> None:
    print(
        json.dumps(
            {
                "run_suffix": reach.run_suffix,
                "condition": reach.condition,
                "turns_parsed": reach.turns_parsed,
                "py_edit_count": reach.py_edit_count,
                "mcp_calls": reach.mcp_calls,
                "cli_calls": reach.cli_calls,
                "hook_firings": reach.hook_firings,
                "hook_firings_with_context": reach.hook_firings_with_context,
                "reached": reach.reached,
                "parse_warnings": reach.parse_warnings,
            }
        )
    )


def _condition_stats(rs: list[SessionReach]) -> dict:
    n = len(rs)
    reached_count = sum(1 for r in rs if r.reached)
    return {
        "n": n,
        "reached_count": reached_count,
        "reached_pct": round(100 * reached_count / n, 1),
        "avg_py_edits": round(sum(r.py_edit_count for r in rs) / n, 1),
        "avg_hook_firings": round(sum(r.hook_firings for r in rs) / n, 1),
        "avg_hook_firings_with_context": round(
            sum(r.hook_firings_with_context for r in rs) / n, 1
        ),
    }


def aggregate(run_id: str, output_format: str) -> None:
    pattern = f"run-{run_id}-*-v6-*"
    dirs = sorted(RESULTS_DIR.glob(pattern))
    if not dirs:
        print(f"ERROR: no results dirs matching {pattern}", file=sys.stderr)
        sys.exit(1)

    reaches = [score_run(d.name.removeprefix("run-")) for d in dirs]

    by_condition: dict[str, list[SessionReach]] = {}
    for r in reaches:
        by_condition.setdefault(r.condition, []).append(r)

    stats_by_condition = {cond: _condition_stats(rs) for cond, rs in by_condition.items()}

    if output_format == "json":
        print(json.dumps(stats_by_condition, indent=2))
        return

    print(f"=== V6 Aggregate: run_id={run_id} ===")
    for cond, stats in stats_by_condition.items():
        n, reached = stats["n"], stats["reached_count"]
        print(f"\n[{cond}] N={n}")
        print(f"  Reached catalog: {reached}/{n} ({stats['reached_pct']}%)")
        print(f"  Avg .py edits/session: {stats['avg_py_edits']}")
        if cond == "guidance-with-hook":
            with_ctx = stats["avg_hook_firings_with_context"]
            avg_fire = stats["avg_hook_firings"]
            print(f"  Avg hook firings/session: {avg_fire} (with context: {with_ctx})")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run_suffix", nargs="?", help="e.g. 1-1-v6-guidance-with-hook")
    parser.add_argument(
        "--aggregate", metavar="RUN_ID", help="aggregate all conditions for a run_id, e.g. 1"
    )
    parser.add_argument("--format", choices=["human", "json"], default="human")
    args = parser.parse_args()

    if args.aggregate:
        aggregate(args.aggregate, args.format)
        return 0

    if not args.run_suffix:
        parser.error("run_suffix is required unless --aggregate is given")

    reach = score_run(args.run_suffix)
    if args.format == "json":
        _print_json(reach)
    else:
        _print_human(reach)
    return 0


if __name__ == "__main__":
    sys.exit(main())
