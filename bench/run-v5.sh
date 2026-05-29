#!/usr/bin/env bash
set -euo pipefail

# V5 Benchmark Runner: 3-variant × 3-granularity system
#
# Each claude -p session runs in an isolated tmpdir, NOT in ~/claude_workspace.
# This prevents auto-backup hooks, workspace contamination, and file collisions.
#
# Usage:
#   ./bench/run-v5.sh <run_id> <control|treatment|both> [options]
#
# Options:
#   --variant a|b|c|all       (default: a)
#   --granularity terse|normal|detailed|all  (default: normal)
#   -N <count>                (default: 1)
#   --dry-run                 Print execution plan without running
#   --budget <usd>            Per-session budget (default: 2.00)

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ID="${1:?Usage: $0 <run_id> <control|treatment|both> [options]}"
SESSION="${2:?Usage: $0 <run_id> <control|treatment|both> [options]}"
shift 2

VARIANTS="a"
GRANULARITIES="normal"
N_RUNS=1
DRY_RUN=false
BUDGET="2.00"
MODEL="${MODEL:-}"
MODEL_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --variant) VARIANTS="$2"; shift 2 ;;
        --granularity) GRANULARITIES="$2"; shift 2 ;;
        -N) N_RUNS="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --budget) BUDGET="$2"; shift 2 ;;
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
    echo "Total sessions: $session_count"
    echo ""
    echo "Prompt files:"
    for v in "${variant_list[@]}"; do
        for g in "${gran_list[@]}"; do
            pf="$REPO_DIR/bench/prompts/v5-${v}-${g}.txt"
            if [ -f "$pf" ]; then echo "  [OK] $pf"; else echo "  [MISSING] $pf"; fi
        done
    done
    exit 0
fi

# --- Pre-flight checks ---
echo "=== V5 Pre-flight Checks ==="

if ! command -v claude &>/dev/null; then
    echo "ERROR: claude CLI not found" >&2; exit 1
fi
echo "[OK] Claude CLI found"

SCORER="$REPO_DIR/bench/score_v5.py"
if [ ! -f "$SCORER" ]; then
    echo "ERROR: Scorer not found: $SCORER" >&2; exit 1
fi
echo "[OK] Scorer found"

for v in "${variant_list[@]}"; do
    for g in "${gran_list[@]}"; do
        pf="$REPO_DIR/bench/prompts/v5-${v}-${g}.txt"
        if [ ! -f "$pf" ]; then
            echo "ERROR: Prompt not found: $pf" >&2; exit 1
        fi
    done
done
echo "[OK] All prompt files found"

RULE_SOURCE="$REPO_DIR/skills/modern-python-guidance/SKILL.md"
if [ ! -f "$RULE_SOURCE" ]; then
    echo "ERROR: Guidance source not found: $RULE_SOURCE" >&2; exit 1
fi
echo "[OK] Guidance source found"
echo ""

# --- Guidance file content (extracted once, reused per session) ---
GUIDANCE_CONTENT=$(awk 'BEGIN{c=0} /^---$/{c++; next} c>=2{print}' "$RULE_SOURCE")

# --- Run a single session in isolated tmpdir ---
run_session() {
    local variant="$1" gran="$2" session_type="$3" run_n="$4"
    local run_suffix="${RUN_ID}-${run_n}-v5${variant}${gran:0:1}"
    local results_dir="$REPO_DIR/results/run-${run_suffix}"
    local prompt="$REPO_DIR/bench/prompts/v5-${variant}-${gran}.txt"
    local log="$results_dir/guidance-verify.log"

    mkdir -p "$results_dir"

    # Create isolated workspace
    local tmpwork
    tmpwork=$(mktemp -d "$HOME/mpg-bench-XXXXXX")

    # Set up .claude/rules/ for guidance toggle
    mkdir -p "$tmpwork/.claude/rules"

    local session_label
    if [ "$session_type" = "control" ]; then
        session_label="a"
        # No guidance file
    else
        session_label="b"
        echo "$GUIDANCE_CONTENT" > "$tmpwork/.claude/rules/modern-python.md"
    fi

    # Record verification
    local rule_file="$tmpwork/.claude/rules/modern-python.md"
    local label_upper
    label_upper="$(echo "${session_type}-V5${variant}${gran}" | tr '[:lower:]' '[:upper:]')"

    echo "=== PRE-${label_upper} $(date -u '+%Y-%m-%dT%H:%M:%SZ') ===" >> "$log"
    echo "TMPWORK=$tmpwork" >> "$log"
    if [ -f "$rule_file" ]; then
        echo "status: PRESENT ($(wc -c < "$rule_file") bytes)" >> "$log"
        shasum -a 256 "$rule_file" >> "$log" 2>/dev/null || true
    else
        echo "status: ABSENT" >> "$log"
    fi
    echo "MODEL=${MODEL:-<default>}" >> "$log"
    echo "" >> "$log"

    # Run claude -p in isolated tmpdir
    echo "[running] claude -p ($session_type, variant $variant, $gran) in $tmpwork ..."
    (cd "$tmpwork" && claude -p ${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"} \
        --output-format json --max-budget-usd "$BUDGET" \
        < "$prompt" > "$results_dir/session-${session_label}.json" \
        2>"$results_dir/session-${session_label}.stderr") || true

    # Post verification
    echo "=== POST-${label_upper} $(date -u '+%Y-%m-%dT%H:%M:%SZ') ===" >> "$log"
    if [ -f "$rule_file" ]; then
        echo "status: PRESENT ($(wc -c < "$rule_file") bytes)" >> "$log"
    else
        echo "status: ABSENT" >> "$log"
    fi
    echo "" >> "$log"

    # Move generated files to results (everything except .claude/)
    mkdir -p "$results_dir/${session_type}"
    for item in "$tmpwork"/*; do
        [ -e "$item" ] || continue
        local base
        base=$(basename "$item")
        [ "$base" = ".claude" ] && continue
        mv "$item" "$results_dir/${session_type}/$base" 2>/dev/null || true
    done
    # Also move hidden dirs that aren't .claude (e.g. .venv created by LLM)
    for item in "$tmpwork"/.*; do
        [ -e "$item" ] || continue
        local base
        base=$(basename "$item")
        case "$base" in .|..|.claude) continue ;; esac
        mv "$item" "$results_dir/${session_type}/$base" 2>/dev/null || true
    done

    # Remove tmpdir
    rm -rf "$tmpwork"

    echo "[ok] $session_type saved to $results_dir/${session_type}/"
}

# --- Main execution ---
echo "=== V5 Benchmark Run $RUN_ID ==="
echo "Variants: ${variant_list[*]}, Granularities: ${gran_list[*]}, N=$N_RUNS"
echo "Sessions: $session_count total"
echo ""

completed=0
start_time=$(date +%s)

for v in "${variant_list[@]}"; do
    for g in "${gran_list[@]}"; do
        for ((n=1; n<=N_RUNS; n++)); do
            if [ "$SESSION" = "control" ] || [ "$SESSION" = "both" ]; then
                completed=$((completed + 1))
                elapsed=$(( $(date +%s) - start_time ))
                if [ "$completed" -gt 1 ]; then
                    remaining=$(( elapsed * (session_count - completed) / (completed - 1) ))
                else
                    remaining=0
                fi
                echo ""
                echo "[$completed/$session_count] Variant $v, $g, Control, run $n — elapsed ${elapsed}s, est ${remaining}s remaining"
                run_session "$v" "$g" "control" "$n"
            fi

            if [ "$SESSION" = "treatment" ] || [ "$SESSION" = "both" ]; then
                completed=$((completed + 1))
                elapsed=$(( $(date +%s) - start_time ))
                if [ "$completed" -gt 1 ]; then
                    remaining=$(( elapsed * (session_count - completed) / (completed - 1) ))
                else
                    remaining=0
                fi
                echo ""
                echo "[$completed/$session_count] Variant $v, $g, Treatment, run $n — elapsed ${elapsed}s, est ${remaining}s remaining"
                run_session "$v" "$g" "treatment" "$n"
            fi

            # Score this run
            echo ""
            echo "--- Scoring run $n, variant $v, $g ---"
            python3 "$SCORER" "${RUN_ID}-${n}-v5${v}${g:0:1}" --variant "$v" || true
        done
    done
done

total_elapsed=$(( $(date +%s) - start_time ))
echo ""
echo "=== V5 Benchmark Complete ==="
echo "Total time: ${total_elapsed}s"
echo ""
echo "Score individual runs:"
for v in "${variant_list[@]}"; do
    for g in "${gran_list[@]}"; do
        for ((n=1; n<=N_RUNS; n++)); do
            echo "  python3 bench/score_v5.py ${RUN_ID}-${n}-v5${v}${g:0:1} --variant $v"
        done
    done
done
