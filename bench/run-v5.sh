#!/usr/bin/env bash
set -euo pipefail

# V5 Benchmark Runner: 3-variant × 3-granularity system
# Usage:
#   ./bench/run-v5.sh <run_id> <control|treatment|both> [options]
#
# Options:
#   --variant a|b|c|all       (default: a)
#   --granularity terse|normal|detailed|all  (default: normal)
#   -N <count>                (default: 1)
#   --dry-run                 Print execution plan without running
#   --budget <usd>            Per-session budget (default: 2.00)
#   --max-total <usd>         Total budget ceiling (default: 40)

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$HOME/claude_workspace"
RUN_ID="${1:?Usage: $0 <run_id> <control|treatment|both> [options]}"
SESSION="${2:?Usage: $0 <run_id> <control|treatment|both> [options]}"
shift 2

VARIANTS="a"
GRANULARITIES="normal"
N_RUNS=1
DRY_RUN=false
BUDGET="2.00"
MAX_TOTAL="40"
MODEL="${MODEL:-}"
MODEL_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --variant) VARIANTS="$2"; shift 2 ;;
        --granularity) GRANULARITIES="$2"; shift 2 ;;
        -N) N_RUNS="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --budget) BUDGET="$2"; shift 2 ;;
        --max-total) MAX_TOTAL="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

if [ -n "$MODEL" ]; then
    MODEL_ARGS=(--model "$MODEL")
fi

# --- Resolve variant/granularity lists ---
variant_list=()
case "$VARIANTS" in
    all) variant_list=(a b c) ;;
    a|b|c) variant_list=("$VARIANTS") ;;
    *) echo "ERROR: Invalid variant '$VARIANTS'" >&2; exit 1 ;;
esac

gran_list=()
case "$GRANULARITIES" in
    all) gran_list=(terse normal detailed) ;;
    terse|normal|detailed) gran_list=("$GRANULARITIES") ;;
    *) echo "ERROR: Invalid granularity '$GRANULARITIES'" >&2; exit 1 ;;
esac

case "$SESSION" in
    control|treatment|both) ;;
    *) echo "ERROR: Invalid session '$SESSION'" >&2; exit 1 ;;
esac

# --- Count total sessions ---
session_count=0
sessions_per_combo=1
if [ "$SESSION" = "both" ]; then sessions_per_combo=2; fi

for _ in "${variant_list[@]}"; do
    for _ in "${gran_list[@]}"; do
        session_count=$((session_count + N_RUNS * sessions_per_combo))
    done
done

est_cost=$(echo "scale=2; $session_count * $BUDGET" | bc)

# --- Dry run ---
if $DRY_RUN; then
    echo "=== V5 Benchmark Dry Run ==="
    echo "Run ID:       $RUN_ID"
    echo "Session:      $SESSION"
    echo "Variants:     ${variant_list[*]}"
    echo "Granularities: ${gran_list[*]}"
    echo "N:            $N_RUNS"
    echo "Model:        ${MODEL:-<default>}"
    echo "Per-session:  \$$BUDGET"
    echo "Max total:    \$$MAX_TOTAL"
    echo ""
    echo "Total sessions: $session_count"
    echo "Est. cost:      \$$est_cost"
    echo "Est. time:      ~$((session_count * 3))min"
    echo ""
    echo "Prompt files:"
    for v in "${variant_list[@]}"; do
        for g in "${gran_list[@]}"; do
            pf="$REPO_DIR/bench/prompts/v5-${v}-${g}.txt"
            if [ -f "$pf" ]; then
                echo "  [OK] $pf"
            else
                echo "  [MISSING] $pf"
            fi
        done
    done
    exit 0
fi

# --- Pre-flight checks ---
echo "=== V5 Pre-flight Checks ==="

# Check Claude CLI
if ! command -v claude &>/dev/null; then
    echo "ERROR: claude CLI not found" >&2
    exit 1
fi
echo "[OK] Claude CLI found"

# Check scorer
SCORER="$REPO_DIR/bench/score_v5.py"
if [ ! -f "$SCORER" ]; then
    echo "ERROR: Scorer not found: $SCORER" >&2
    exit 1
fi
echo "[OK] Scorer found"

# Check prompt files
for v in "${variant_list[@]}"; do
    for g in "${gran_list[@]}"; do
        pf="$REPO_DIR/bench/prompts/v5-${v}-${g}.txt"
        if [ ! -f "$pf" ]; then
            echo "ERROR: Prompt not found: $pf" >&2
            exit 1
        fi
    done
done
echo "[OK] All prompt files found"

# Check guidance source
RULE_SOURCE="$REPO_DIR/skills/modern-python-guidance/SKILL.md"
if [ ! -f "$RULE_SOURCE" ]; then
    echo "ERROR: Guidance source not found: $RULE_SOURCE" >&2
    exit 1
fi
echo "[OK] Guidance source found"

# Cost check
if (( $(echo "$est_cost > $MAX_TOTAL" | bc -l) )); then
    echo "ERROR: Estimated cost \$$est_cost exceeds MAX_TOTAL \$$MAX_TOTAL" >&2
    echo "Reduce N, variants, or granularities, or increase --max-total" >&2
    exit 1
fi
echo "[OK] Est. cost \$$est_cost within budget \$$MAX_TOTAL"
echo ""

# --- Guidance toggle ---
RULE_FILE="$WORKSPACE/.claude/rules/modern-python.md"

disable_guidance() {
    rm -f "$RULE_FILE"
}

enable_guidance() {
    if [ ! -f "$RULE_FILE" ]; then
        awk 'BEGIN{c=0} /^---$/{c++; next} c>=2{print}' "$RULE_SOURCE" > "$RULE_FILE"
    fi
}

restore_guidance_on_exit() {
    enable_guidance
    echo "[cleanup] Rules file restored."
}

record_verify() {
    local label="$1" log="$2"
    echo "=== $label $(date -u '+%Y-%m-%dT%H:%M:%SZ') ===" >> "$log"
    echo "RULE_FILE=$RULE_FILE" >> "$log"
    if [ -f "$RULE_FILE" ]; then
        echo "status: PRESENT ($(wc -c < "$RULE_FILE") bytes)" >> "$log"
        shasum -a 256 "$RULE_FILE" >> "$log" 2>/dev/null || true
    else
        echo "status: ABSENT" >> "$log"
    fi
    echo "MODEL=${MODEL:-<default>}" >> "$log"
    echo "" >> "$log"
}

# --- Cleanup generated files ---
cleanup_variant() {
    local variant="$1" dest="$2"
    mkdir -p "$dest"
    case "$variant" in
        a)
            [ -d "$WORKSPACE/src" ] && mv "$WORKSPACE/src" "$dest/src" || true
            [ -f "$WORKSPACE/pyproject.toml" ] && mv "$WORKSPACE/pyproject.toml" "$dest/pyproject.toml" || true
            [ -f "$WORKSPACE/setup.py" ] && mv "$WORKSPACE/setup.py" "$dest/setup.py" || true
            ;;
        b)
            [ -d "$WORKSPACE/myapp" ] && mv "$WORKSPACE/myapp" "$dest/myapp" || true
            ;;
        c)
            [ -d "$WORKSPACE/tests" ] && mv "$WORKSPACE/tests" "$dest/tests" || true
            ;;
    esac
}

# --- Cost tracking ---
TOTAL_SPENT="0"

update_cost() {
    local json_file="$1"
    if [ -f "$json_file" ]; then
        local cost
        cost=$(python3 -c "
import json, sys
try:
    d = json.load(open('$json_file'))
    print(d.get('usage', {}).get('total_cost_usd', d.get('cost_usd', 0)) or 0)
except: print(0)
" 2>/dev/null)
        TOTAL_SPENT=$(echo "$TOTAL_SPENT + $cost" | bc)
    fi
}

check_budget() {
    if (( $(echo "$TOTAL_SPENT > $MAX_TOTAL" | bc -l) )); then
        echo ""
        echo "BUDGET EXCEEDED: spent \$$TOTAL_SPENT > max \$$MAX_TOTAL"
        echo "Stopping execution."
        restore_guidance_on_exit
        exit 1
    fi
}

# --- Run a single session ---
run_session() {
    local variant="$1" gran="$2" session_type="$3" run_n="$4"
    local run_suffix="${RUN_ID}-${run_n}-v5${variant}${gran:0:1}"
    local results_dir="$REPO_DIR/results/run-${run_suffix}"
    local prompt="$REPO_DIR/bench/prompts/v5-${variant}-${gran}.txt"
    local log="$results_dir/guidance-verify.log"

    mkdir -p "$results_dir"

    local session_label
    if [ "$session_type" = "control" ]; then
        session_label="a"
        disable_guidance
        trap restore_guidance_on_exit EXIT
        if [ -f "$RULE_FILE" ]; then
            echo "ERROR: Rules file still exists after rm!" >&2; exit 1
        fi
    else
        session_label="b"
        enable_guidance
        trap - EXIT
        if [ ! -f "$RULE_FILE" ]; then
            echo "ERROR: Rules file not found!" >&2; exit 1
        fi
    fi

    record_verify "PRE-${session_type^^}-V5${variant^^}${gran^^}" "$log"

    echo "[running] claude -p ($session_type, variant $variant, $gran) ..."
    (cd "$WORKSPACE" && claude -p ${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"} \
        --output-format json --max-budget-usd "$BUDGET" \
        < "$prompt" > "$results_dir/session-${session_label}.json" \
        2>"$results_dir/session-${session_label}.stderr") || true

    record_verify "POST-${session_type^^}-V5${variant^^}${gran^^}" "$log"
    cleanup_variant "$variant" "$results_dir/${session_type}"

    update_cost "$results_dir/session-${session_label}.json"
    check_budget

    echo "[ok] $session_type saved. Spent: \$$TOTAL_SPENT / \$$MAX_TOTAL"
}

# --- Main execution ---
echo "=== V5 Benchmark Run $RUN_ID ==="
echo "Variants: ${variant_list[*]}, Granularities: ${gran_list[*]}, N=$N_RUNS"
echo "Est. cost: \$$est_cost, Max: \$$MAX_TOTAL"
echo ""

completed=0
start_time=$(date +%s)

for v in "${variant_list[@]}"; do
    for g in "${gran_list[@]}"; do
        for ((n=1; n<=N_RUNS; n++)); do
            if [ "$SESSION" = "control" ] || [ "$SESSION" = "both" ]; then
                completed=$((completed + 1))
                elapsed=$(( $(date +%s) - start_time ))
                remaining=$(( elapsed * (session_count - completed) / (completed > 0 ? completed : 1) ))
                echo ""
                echo "[$completed/$session_count] Variant $v, $g, Control, run $n — elapsed ${elapsed}s, est remaining ${remaining}s"
                run_session "$v" "$g" "control" "$n"
            fi

            if [ "$SESSION" = "treatment" ] || [ "$SESSION" = "both" ]; then
                completed=$((completed + 1))
                elapsed=$(( $(date +%s) - start_time ))
                remaining=$(( elapsed * (session_count - completed) / (completed > 0 ? completed : 1) ))
                echo ""
                echo "[$completed/$session_count] Variant $v, $g, Treatment, run $n — elapsed ${elapsed}s, est remaining ${remaining}s"
                run_session "$v" "$g" "treatment" "$n"
            fi

            # Score this run
            echo ""
            echo "--- Scoring run $n, variant $v, $g ---"
            python3 "$SCORER" "${RUN_ID}-${n}-v5${v}${g:0:1}" --variant "$v" || true
        done
    done
done

restore_guidance_on_exit

total_elapsed=$(( $(date +%s) - start_time ))
echo ""
echo "=== V5 Benchmark Complete ==="
echo "Total time: ${total_elapsed}s"
echo "Total spent: \$$TOTAL_SPENT / \$$MAX_TOTAL"
echo ""
echo "Score individual runs:"
for v in "${variant_list[@]}"; do
    for g in "${gran_list[@]}"; do
        for ((n=1; n<=N_RUNS; n++)); do
            echo "  python3 bench/score_v5.py ${RUN_ID}-${n}-v5${v}${g:0:1} --variant $v"
        done
    done
done
