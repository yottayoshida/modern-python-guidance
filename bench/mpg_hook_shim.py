#!/usr/bin/env python3
"""Bench-only shim between Claude Code's PostToolUse hook call and the real
`mpg hook claude-post-tool-use`.

The v6 reach benchmark needs to know whether the hook actually fired and
whether it injected additionalContext, independent of whatever a session's
--output-format stream-json transcript happens to expose. This shim sits in
place of the real hook command, forwards the call unchanged, and appends one
JSONL line per invocation to ./.mpg-bench-hook.log (relative to the hook's
cwd -- the bench session's isolated tmpdir).

Not part of the installable package; only used by bench/run-v6.sh, which
rewrites settings.local.json to route through this shim after `mpg setup`
has written the real hook entry.

Usage (as installed into the hook's command+args by run-v6.sh):
    <python> mpg_hook_shim.py <real-mpg-interpreter-path>
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

from modern_python_guidance.hook_config import HOOK_SUBCOMMAND


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: mpg_hook_shim.py <real-interpreter-path>", file=sys.stderr)
        return 1
    real_python = sys.argv[1]
    stdin_data = sys.stdin.read()

    proc = subprocess.run(
        [real_python, "-m", "modern_python_guidance", "hook", HOOK_SUBCOMMAND],
        input=stdin_data,
        capture_output=True,
        text=True,
    )

    additional_context = None
    parse_error = False
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
            additional_context = payload.get("hookSpecificOutput", {}).get("additionalContext")
        except json.JSONDecodeError:
            parse_error = True

    log_entry = {
        "ts": time.time(),
        "exit_code": proc.returncode,
        "additional_context_present": bool(additional_context),
        "additional_context_len": len(additional_context) if additional_context else 0,
    }
    if parse_error:
        log_entry["parse_error"] = True

    with open(".mpg-bench-hook.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
