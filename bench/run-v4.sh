#!/usr/bin/env bash
set -euo pipefail

# V4 Benchmark Runner: 3-variant system
# Usage:
#   ./bench/run-v4.sh <run_id> <control|treatment|both> [--variant a|b|c|all]
#
# Variants:
#   a — FastAPI + async ecosystem (7 files, 32 scored + 1 info)
#   b — Django (3 files, 3 scored)
#   c — pytest (1 file, 3 scored)
#   all — run all 3 variants sequentially (default)

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$HOME/claude_workspace"
RUN_ID="${1:?Usage: $0 <run_id> <control|treatment|both> [--variant a|b|c|all]}"
SESSION="${2:?Usage: $0 <run_id> <control|treatment|both> [--variant a|b|c|all]}"
shift 2

VARIANTS="all"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --variant) VARIANTS="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

BUDGET="2.00"

# --- Optional model pin (opt-in via MODEL env; no-op when unset) ---
MODEL="${MODEL:-}"
MODEL_ARGS=()
if [ -n "$MODEL" ]; then
    MODEL_ARGS=(--model "$MODEL")
    echo "[config] Pinning model: $MODEL"
fi

# --- Guidance toggle: rules/ file ---
RULE_FILE="$WORKSPACE/.claude/rules/modern-python.md"
RULE_SOURCE="$REPO_DIR/skills/modern-python-guidance/SKILL.md"

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

# --- Verification logging ---
record_verify() {
    local label="$1" log="$2"
    echo "=== $label $(date -u '+%Y-%m-%dT%H:%M:%SZ') ===" >> "$log"
    echo "RULE_FILE=$RULE_FILE" >> "$log"
    if [ -f "$RULE_FILE" ]; then
        echo "status: PRESENT ($(wc -c < "$RULE_FILE") bytes)" >> "$log"
    else
        echo "status: ABSENT" >> "$log"
    fi
    echo "" >> "$log"
}

variant_prompt() {
    local variant="$1"
    echo "$REPO_DIR/bench/prompt-v4-${variant}.txt"
}

# --- Workspace cleanup for a variant ---
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

# --- Run a single variant session ---
run_variant_session() {
    local variant="$1" session_type="$2" run_id="$3"
    local variant_run_id="${run_id}-v4${variant}"
    local results_dir="$REPO_DIR/results/run-${variant_run_id}"
    local prompt
    prompt=$(variant_prompt "$variant")
    local log="$results_dir/guidance-verify.log"

    if [ ! -f "$prompt" ]; then
        echo "ERROR: Prompt not found: $prompt" >&2
        return 1
    fi

    mkdir -p "$results_dir"

    if [ "$session_type" = "control" ] || [ "$session_type" = "both" ]; then
        echo ""
        echo "--- Variant $variant: Control (guidance DISABLED) ---"
        disable_guidance
        trap restore_guidance_on_exit EXIT

        if [ -f "$RULE_FILE" ]; then
            echo "ERROR: Rules file still exists after rm!" >&2
            exit 1
        fi
        record_verify "PRE-CONTROL-V4$(echo "$variant" | tr '[:lower:]' '[:upper:]')" "$log"

        echo "[running] claude -p (Control, variant $variant) from $WORKSPACE ..."
        echo "MODEL=${MODEL:-<default>}" >> "$log"
        (cd "$WORKSPACE" && claude -p ${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"} --output-format json --max-budget-usd "$BUDGET" \
            < "$prompt" > "$results_dir/session-a.json" 2>"$results_dir/session-a.stderr") || true

        record_verify "POST-CONTROL-V4$(echo "$variant" | tr '[:lower:]' '[:upper:]')" "$log"
        cleanup_variant "$variant" "$results_dir/control"
        echo "[ok] Control files saved to $results_dir/control/"
    fi

    if [ "$session_type" = "treatment" ] || [ "$session_type" = "both" ]; then
        echo ""
        echo "--- Variant $variant: Treatment (guidance ENABLED) ---"
        enable_guidance
        trap - EXIT

        if [ ! -f "$RULE_FILE" ]; then
            echo "ERROR: Rules file not found at $RULE_FILE" >&2
            exit 1
        fi
        record_verify "PRE-TREATMENT-V4$(echo "$variant" | tr '[:lower:]' '[:upper:]')" "$log"

        echo "[running] claude -p (Treatment, variant $variant) from $WORKSPACE ..."
        echo "MODEL=${MODEL:-<default>}" >> "$log"
        (cd "$WORKSPACE" && claude -p ${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"} --output-format json --max-budget-usd "$BUDGET" \
            < "$prompt" > "$results_dir/session-b.json" 2>"$results_dir/session-b.stderr") || true

        record_verify "POST-TREATMENT-V4$(echo "$variant" | tr '[:lower:]' '[:upper:]')" "$log"
        cleanup_variant "$variant" "$results_dir/treatment"
        echo "[ok] Treatment files saved to $results_dir/treatment/"
    fi

    # Score this variant
    echo ""
    echo "--- Scoring Variant $variant ---"
    VARIANT="$variant" "$REPO_DIR/bench/score-v4.sh" "$variant_run_id" || true
}

# --- Pre-flight checks ---
if [ ! -f "$RULE_SOURCE" ]; then
    echo "ERROR: Guidance source not found at $RULE_SOURCE" >&2
    exit 1
fi

case "$SESSION" in
    control|treatment|both) ;;
    *)
        echo "ERROR: Invalid session '$SESSION'. Use: control, treatment, or both" >&2
        exit 1
        ;;
esac

# --- Determine which variants to run ---
variant_list=()
case "$VARIANTS" in
    all) variant_list=(a b c) ;;
    a|b|c) variant_list=("$VARIANTS") ;;
    *)
        echo "ERROR: Invalid variant '$VARIANTS'. Use: a, b, c, or all" >&2
        exit 1
        ;;
esac

echo "=== V4 Benchmark Run $RUN_ID ($SESSION) ==="
echo "Variants: ${variant_list[*]}"
echo ""

# --- Execute ---
for v in "${variant_list[@]}"; do
    run_variant_session "$v" "$SESSION" "$RUN_ID"
done

echo ""
echo "=== V4 Benchmark Run $RUN_ID Complete ==="
echo ""
echo "Score individual variants:"
for v in "${variant_list[@]}"; do
    echo "  VARIANT=$v ./bench/score-v4.sh ${RUN_ID}-v4${v}"
done
