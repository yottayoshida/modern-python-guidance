#!/usr/bin/env bash
set -euo pipefail

# V6 Reach Benchmark: does an organic multi-turn .py-editing session ever
# actually reference the mpg catalog (MCP tool_use or CLI mpg
# retrieve/search/check), stratified by guidance condition?
#
# Unlike V5 (single-prompt pattern-adoption scoring), V6 measures whether
# the catalog is ever *reached* across a chained multi-turn organic coding
# session that never mentions mpg/MCP by name.
#
# Conditions:
#   baseline            no mpg artifacts at all
#   guidance-no-hook    mpg setup --scope local --no-hook   (MCP+Skills+Rules, no hook)
#   guidance-with-hook  mpg setup --scope local --with-hook (MCP+Skills+Rules+hook)
#
# Each session runs in an isolated tmpdir under $HOME (never inside
# ~/claude_workspace, per workspace-isolation.md), turns are chained via
# `claude -p --resume` through the bench/prompts/v6-turns/ sequence, and
# --output-format stream-json is used so individual tool_use blocks (not
# just final text) can be counted -- grep-over-final-text is a known false
# positive/negative risk for this metric.
#
# For guidance-with-hook, the hook entry mpg setup writes is rewritten to
# route through mpg_hook_shim.py so hook firing/additionalContext can be
# logged independent of the transcript.
#
# Usage:
#   ./bench/run-v6.sh <run_id> <baseline|guidance-no-hook|guidance-with-hook|all> [options]
#
# Options:
#   -N <count>                (default: 1)
#   --dry-run                 Print execution plan without running
#   --allow-credit-use        Required for non-dry-run execution; claude -p may consume credits
#   --budget <usd>            Per-turn budget (default: 3.00)

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ID="${1:?Usage: $0 <run_id> <baseline|guidance-no-hook|guidance-with-hook|all> [options]}"
CONDITION="${2:?Usage: $0 <run_id> <baseline|guidance-no-hook|guidance-with-hook|all> [options]}"
shift 2

N_RUNS=1
DRY_RUN=false
ALLOW_CREDIT_USE=false
BUDGET="3.00"
MODEL="${MODEL:-}"
MODEL_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -N) N_RUNS="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --allow-credit-use) ALLOW_CREDIT_USE=true; shift ;;
        --budget) BUDGET="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

if [ -n "$MODEL" ]; then
    MODEL_ARGS=(--model "$MODEL")
fi

condition_list=()
case "$CONDITION" in
    all) condition_list=(baseline guidance-no-hook guidance-with-hook) ;;
    baseline|guidance-no-hook|guidance-with-hook) condition_list=("$CONDITION") ;;
    *) echo "ERROR: Invalid condition '$CONDITION'" >&2; exit 1 ;;
esac

TURNS_DIR="$REPO_DIR/bench/prompts/v6-turns"
turn_files=()
while IFS= read -r -d '' f; do turn_files+=("$f"); done < <(find "$TURNS_DIR" -name 'turn-*.txt' -print0 | sort -z)
if [ "${#turn_files[@]}" -eq 0 ]; then
    echo "ERROR: No turn prompts found in $TURNS_DIR" >&2
    exit 1
fi

session_count=$(( ${#condition_list[@]} * N_RUNS ))

# --- Dry run ---
if $DRY_RUN; then
    echo "=== V6 Reach Benchmark Dry Run ==="
    echo "Run ID:          $RUN_ID"
    echo "Conditions:      ${condition_list[*]}"
    echo "Turns/session:   ${#turn_files[@]}"
    echo "N:               $N_RUNS"
    echo "Model:           ${MODEL:-<default>}"
    echo "Per-turn budget: \$$BUDGET"
    echo "Total sessions:  $session_count (each = ${#turn_files[@]} chained turns)"
    echo "Credit use:      none (--dry-run)"
    echo "To execute:      re-run without --dry-run and add --allow-credit-use"
    echo ""
    echo "Turn prompts:"
    for f in "${turn_files[@]}"; do echo "  [OK] $f"; done
    exit 0
fi

if ! $ALLOW_CREDIT_USE; then
    cat >&2 <<'EOF'
ERROR: V6 reach benchmark calls claude -p across multiple chained turns per
session and may consume substantial Claude credits -- more than a single
V5 prompt. Re-run with --allow-credit-use only after reviewing the
session/turn count and budget with --dry-run first.
EOF
    exit 2
fi

# --- Pre-flight checks ---
echo "=== V6 Pre-flight Checks ==="

if ! command -v claude &>/dev/null; then
    echo "ERROR: claude CLI not found" >&2; exit 1
fi
echo "[OK] Claude CLI found"

MPG_PYTHON="$REPO_DIR/.venv/bin/python3"
if [ ! -x "$MPG_PYTHON" ]; then
    echo "ERROR: mpg venv interpreter not found: $MPG_PYTHON (run 'uv venv && uv pip install -e \".[dev]\"' first)" >&2
    exit 1
fi
echo "[OK] mpg interpreter found"

SHIM="$REPO_DIR/bench/mpg_hook_shim.py"
if [ ! -f "$SHIM" ]; then
    echo "ERROR: hook shim not found: $SHIM" >&2; exit 1
fi
echo "[OK] Hook shim found"

SCORER="$REPO_DIR/bench/score_v6.py"
if [ ! -f "$SCORER" ]; then
    echo "ERROR: Scorer not found: $SCORER" >&2; exit 1
fi
echo "[OK] Scorer found"
echo ""

# --- Rewrite the mpg hook entry to route through the logging shim ---
# Bench-only instrumentation; production `mpg setup` never does this. Reuses
# hook_config.py's own read/identify/write contract (fail-closed, atomic,
# the same exact-word entry match `mpg setup` itself relies on) instead of
# re-parsing settings.local.json by hand -- and exits loudly if no matching
# entry is found, rather than silently leaving the hook unshimmed.
#
# Not idempotent by design: the rewritten entry's args no longer contain
# HOOK_SUBCOMMAND, so a second call would not find a match and would exit
# loudly rather than double-wrap. Fine as-is -- each tmpdir only ever calls
# this once, right after `mpg setup --with-hook`.
inject_shim() {
    local tmpwork="$1"
    "$MPG_PYTHON" - "$tmpwork" "$SHIM" <<'PYEOF'
import sys
from pathlib import Path

from modern_python_guidance.hook_config import (
    _is_mpg_entry,
    find_mpg_group,
    read_settings,
    settings_local_path,
    write_settings_atomic,
)

tmpwork, shim = Path(sys.argv[1]), sys.argv[2]
settings_path = settings_local_path(tmpwork)
settings = read_settings(settings_path)
group = find_mpg_group(settings)
if group is None:
    sys.exit(f"ERROR: no mpg PostToolUse group found in {settings_path} -- shim not installed")

matched = False
for entry in group.get("hooks", []):
    if _is_mpg_entry(entry):
        entry["args"] = [shim, entry["command"]]
        matched = True

if not matched:
    sys.exit(f"ERROR: mpg PostToolUse group in {settings_path} has no matching entry -- shim not installed")

write_settings_atomic(settings_path, settings)
PYEOF
}

# --- Set up a tmpdir for one of the 3 conditions ---
setup_condition() {
    local tmpwork="$1" condition="$2"
    case "$condition" in
        baseline)
            ;;
        guidance-no-hook)
            "$MPG_PYTHON" -m modern_python_guidance setup \
                --project-dir "$tmpwork" --scope local --no-hook >/dev/null
            ;;
        guidance-with-hook)
            "$MPG_PYTHON" -m modern_python_guidance setup \
                --project-dir "$tmpwork" --scope local --with-hook >/dev/null
            inject_shim "$tmpwork"
            ;;
    esac
}

# --- Extract session_id from a stream-json transcript (first line that has one) ---
extract_session_id() {
    local transcript="$1"
    "$MPG_PYTHON" -c "
import json
import sys

with open(sys.argv[1]) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        sid = obj.get('session_id')
        if sid:
            print(sid)
            break
" "$transcript"
}

# --- Teardown: unregister the local-scope MCP entry mpg setup wrote (it lives
# in the REAL global ~/.claude.json, keyed by project path -- Claude Code's
# "local" scope is personal-but-still-global, not project-local -- so it
# must be explicitly removed before the tmpdir it was keyed to disappears,
# or it orphans there permanently) before deleting the tmpdir itself.
CURRENT_TMPWORK=""
CURRENT_CONDITION=""

cleanup_current() {
    if [ -n "$CURRENT_TMPWORK" ] && [ -d "$CURRENT_TMPWORK" ]; then
        if [ "$CURRENT_CONDITION" != "baseline" ]; then
            (cd "$CURRENT_TMPWORK" && claude mcp remove mpg --scope local) >/dev/null 2>&1 || true
        fi
        rm -rf "$CURRENT_TMPWORK"
    fi
    CURRENT_TMPWORK=""
}
# A trap with no explicit `exit` does not terminate the script -- bash just
# runs the handler and continues (the current session's own `claude -p`
# child does die from Ctrl+C hitting the whole foreground process group,
# but the *script* would otherwise proceed straight into the next paid
# session). INT/TERM must exit explicitly; EXIT must not (it already fires
# once at every exit path, explicit or not).
trap cleanup_current EXIT
trap 'cleanup_current; exit 130' INT TERM

# --- Run one full (multi-turn) session for one condition ---
run_session() {
    local condition="$1" run_n="$2"
    local run_suffix="${RUN_ID}-${run_n}-v6-${condition}"
    local results_dir="$REPO_DIR/results/run-${run_suffix}"
    mkdir -p "$results_dir"

    local tmpwork
    tmpwork=$(mktemp -d "$HOME/mpg-bench-v6-XXXXXX")
    CURRENT_TMPWORK="$tmpwork"
    CURRENT_CONDITION="$condition"

    setup_condition "$tmpwork" "$condition"

    local session_id=""
    local turn_n=0
    for prompt in "${turn_files[@]}"; do
        turn_n=$((turn_n + 1))
        local turn_log="$results_dir/turn-${turn_n}.stream.jsonl"
        echo "[running] $condition run $run_n, turn $turn_n/${#turn_files[@]} in $tmpwork ..."

        local resume_args=()
        [ -n "$session_id" ] && resume_args=(--resume "$session_id")
        (cd "$tmpwork" && claude -p ${resume_args[@]+"${resume_args[@]}"} ${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"} \
            --output-format stream-json --verbose --max-budget-usd "$BUDGET" \
            < "$prompt" > "$turn_log" \
            2>"$results_dir/turn-${turn_n}.stderr") || true

        local next_id
        next_id=$(extract_session_id "$turn_log" 2>/dev/null || true)
        if [ -n "$next_id" ]; then
            session_id="$next_id"
        elif [ -n "$session_id" ]; then
            echo "[warn] could not extract session_id after turn $turn_n; turn $((turn_n + 1)) (if any) will retry --resume with the last known session_id ($session_id) rather than this turn's" >&2
        else
            echo "[warn] could not extract session_id after turn $turn_n; turn $((turn_n + 1)) (if any) will start a fresh session instead of resuming" >&2
        fi
    done

    if [ -f "$tmpwork/.mpg-bench-hook.log" ]; then
        cp "$tmpwork/.mpg-bench-hook.log" "$results_dir/hook-shim.log"
    fi

    cleanup_current
    echo "[ok] $condition run $run_n saved to $results_dir/"

    echo ""
    echo "--- Scoring $condition run $run_n ---"
    "$MPG_PYTHON" "$SCORER" "$run_suffix" || true
}

# --- Main execution ---
echo "=== V6 Reach Benchmark Run $RUN_ID ==="
echo "Conditions: ${condition_list[*]}, N=$N_RUNS, turns/session=${#turn_files[@]}"
echo "Sessions: $session_count total"
echo ""

completed=0
start_time=$(date +%s)

for c in "${condition_list[@]}"; do
    for ((n=1; n<=N_RUNS; n++)); do
        completed=$((completed + 1))
        elapsed=$(( $(date +%s) - start_time ))
        echo ""
        echo "[$completed/$session_count] Condition $c, run $n — elapsed ${elapsed}s"
        run_session "$c" "$n"
    done
done

total_elapsed=$(( $(date +%s) - start_time ))
echo ""
echo "=== V6 Benchmark Complete ==="
echo "Total time: ${total_elapsed}s"
echo ""
echo "Score individual runs:"
for c in "${condition_list[@]}"; do
    for ((n=1; n<=N_RUNS; n++)); do
        echo "  python3 bench/score_v6.py ${RUN_ID}-${n}-v6-${c}"
    done
done
echo ""
echo "Aggregate across a run_id:"
echo "  python3 bench/score_v6.py --aggregate $RUN_ID"
