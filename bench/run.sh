#!/usr/bin/env bash
set -euo pipefail

# Effectiveness Benchmark: A/B test for SKILL.md pre-generation guidance
# Usage:
#   ./bench/run.sh <run_id> control    — Run Session A (skill disabled)
#   ./bench/run.sh <run_id> treatment  — Run Session B (skill enabled)
#   ./bench/run.sh <run_id> both       — Run A then B sequentially

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$HOME/claude_workspace"
RUN_ID="${1:?Usage: $0 <run_id> <control|treatment|both>}"
SESSION="${2:?Usage: $0 <run_id> <control|treatment|both>}"
RESULTS_DIR="$REPO_DIR/results/run-${RUN_ID}"
# Switch prompt version: prompt.txt (v1), prompt-v2.txt (v2), prompt-v3.txt (v3)
PROMPT_FILE="$REPO_DIR/bench/prompt-v3.txt"
BUDGET="2.00"

GEN_SRC="$WORKSPACE/src"
GEN_PYPROJECT="$WORKSPACE/pyproject.toml"

# --- Guidance toggle: rules/ file (not skills/) ---
# Skills body is NOT loaded in pipe mode (claude -p). Only description is visible.
# Rules files (.claude/rules/*.md) without paths: are always loaded into system prompt.
# Toggle by adding/removing the rules file.
RULE_FILE="$WORKSPACE/.claude/rules/modern-python.md"
RULE_SOURCE="$REPO_DIR/skills/modern-python-guidance/SKILL.md"

disable_guidance() {
    rm -f "$RULE_FILE"
}

enable_guidance() {
    if [ ! -f "$RULE_FILE" ]; then
        # Copy body only (strip YAML frontmatter between --- markers)
        awk 'BEGIN{c=0} /^---$/{c++; next} c>=2{print}' "$RULE_SOURCE" > "$RULE_FILE"
    fi
}

restore_guidance_on_exit() {
    enable_guidance
    echo "[cleanup] Rules file restored."
}

# --- Verification logging ---
record_verify() {
    local label="$1"
    local log="$RESULTS_DIR/guidance-verify.log"

    echo "=== $label $(date -u '+%Y-%m-%dT%H:%M:%SZ') ===" >> "$log"

    # Rules file state (primary toggle mechanism)
    echo "RULE_FILE=$RULE_FILE" >> "$log"
    if [ -f "$RULE_FILE" ]; then
        echo "status: PRESENT ($(wc -c < "$RULE_FILE") bytes)" >> "$log"
        echo "first_line: $(head -1 "$RULE_FILE")" >> "$log"
    else
        echo "status: ABSENT" >> "$log"
    fi

    # Check for other rules that might contain Python guidance
    echo "--- all rules files ---" >> "$log"
    ls "$WORKSPACE/.claude/rules/" 2>/dev/null | grep -v '^\.' >> "$log" || echo "(empty)" >> "$log"

    echo "" >> "$log"
}

# --- Workspace cleanup ---
cleanup_generated() {
    local dest="$1"
    mkdir -p "$dest"

    # Primary: files at $WORKSPACE/src/
    if [ -d "$GEN_SRC" ]; then
        mv "$GEN_SRC" "$dest/src"
        [ -f "$GEN_PYPROJECT" ] && mv "$GEN_PYPROJECT" "$dest/pyproject.toml"
    else
        # Fallback: CC may create a project subdirectory
        local found_dir
        found_dir=$(find "$WORKSPACE" -maxdepth 2 -name "models.py" -path "*/src/models.py" \
            -newer "$RESULTS_DIR" -not -path "*/.venv/*" -not -path "*/modern-python-guidance/*" \
            -not -path "*/__bench_backup*" 2>/dev/null | head -1)
        if [ -n "$found_dir" ]; then
            local project_dir
            project_dir=$(dirname "$(dirname "$found_dir")")
            echo "[fallback] Found generated files in $project_dir"
            [ -d "$project_dir/src" ] && mv "$project_dir/src" "$dest/src"
            [ -f "$project_dir/pyproject.toml" ] && mv "$project_dir/pyproject.toml" "$dest/pyproject.toml"
            rmdir "$project_dir" 2>/dev/null || true
        else
            echo "[warning] No generated files found to capture"
            return
        fi
    fi

    # Sweep: capture any other generated files at workspace root
    # (CC may create __init__.py, README.md, requirements.txt etc.)
    local sweep_dir="$dest/extra"
    for f in "$WORKSPACE"/__init__.py "$WORKSPACE"/README.md "$WORKSPACE"/requirements.txt \
             "$WORKSPACE"/setup.py "$WORKSPACE"/setup.cfg; do
        if [ -f "$f" ] && [ "$f" -nt "$RESULTS_DIR" ]; then
            mkdir -p "$sweep_dir"
            mv "$f" "$sweep_dir/"
            echo "[sweep] Captured extra file: $(basename "$f")"
        fi
    done

    # Also remove leftover pyproject.toml if not already moved
    [ -f "$GEN_PYPROJECT" ] && mv "$GEN_PYPROJECT" "$dest/pyproject.toml" 2>/dev/null || true
}

# --- Session runners ---
run_control() {
    echo ""
    echo "--- Session A: Control (guidance DISABLED) ---"

    disable_guidance
    trap restore_guidance_on_exit EXIT

    # Verify rules file is gone
    if [ -f "$RULE_FILE" ]; then
        echo "ERROR: Rules file still exists after rm!" >&2
        exit 1
    fi
    record_verify "PRE-CONTROL"
    echo "[ok] Rules file removed (verified)"

    # Clean workspace
    if [ -d "$GEN_SRC" ]; then
        BACKUP="$WORKSPACE/src.__bench_backup_$(date +%s)__"
        echo "[warning] Existing $GEN_SRC found. Moving to $BACKUP"
        mv "$GEN_SRC" "$BACKUP"
    fi

    # Run CC
    echo "[running] claude -p (Control) from $WORKSPACE ..."
    (cd "$WORKSPACE" && claude -p --output-format json --max-budget-usd "$BUDGET" \
        < "$PROMPT_FILE" > "$RESULTS_DIR/session-a.json" 2>"$RESULTS_DIR/session-a.stderr") || true

    record_verify "POST-CONTROL"
    cleanup_generated "$RESULTS_DIR/control"
    echo "[ok] Control files saved to $RESULTS_DIR/control/"

    # Restore guidance if running control only
    if [ "$SESSION" = "control" ]; then
        enable_guidance
        trap - EXIT
        echo "[ok] Rules file restored."
    fi
}

run_treatment() {
    echo ""
    echo "--- Session B: Treatment (guidance ENABLED) ---"

    enable_guidance
    trap - EXIT

    if [ ! -f "$RULE_FILE" ]; then
        echo "ERROR: Rules file not found at $RULE_FILE" >&2
        exit 1
    fi
    record_verify "PRE-TREATMENT"
    echo "[ok] Rules file present ($(wc -c < "$RULE_FILE") bytes, verified)"

    # Clean workspace
    if [ -d "$GEN_SRC" ]; then
        BACKUP="$WORKSPACE/src.__bench_backup_$(date +%s)__"
        echo "[warning] Existing $GEN_SRC found. Moving to $BACKUP"
        mv "$GEN_SRC" "$BACKUP"
    fi

    # Run CC
    echo "[running] claude -p (Treatment) from $WORKSPACE ..."
    (cd "$WORKSPACE" && claude -p --output-format json --max-budget-usd "$BUDGET" \
        < "$PROMPT_FILE" > "$RESULTS_DIR/session-b.json" 2>"$RESULTS_DIR/session-b.stderr") || true

    record_verify "POST-TREATMENT"
    cleanup_generated "$RESULTS_DIR/treatment"
    echo "[ok] Treatment files saved to $RESULTS_DIR/treatment/"
}

# --- Pre-flight checks ---
if [ ! -f "$PROMPT_FILE" ]; then
    echo "ERROR: prompt.txt not found at $PROMPT_FILE" >&2
    exit 1
fi

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

if [ "$SESSION" = "control" ] && [ -f "$RESULTS_DIR/session-a.json" ]; then
    echo "ERROR: Control session already exists in $RESULTS_DIR" >&2
    exit 1
fi
if [ "$SESSION" = "treatment" ] && [ -f "$RESULTS_DIR/session-b.json" ]; then
    echo "ERROR: Treatment session already exists in $RESULTS_DIR" >&2
    exit 1
fi
if [ "$SESSION" = "both" ] && [ -d "$RESULTS_DIR" ]; then
    echo "ERROR: Results directory already exists: $RESULTS_DIR" >&2
    exit 1
fi

mkdir -p "$RESULTS_DIR"

echo "=== Effectiveness Benchmark Run $RUN_ID ($SESSION) ==="
echo "Prompt: $PROMPT_FILE"
echo "Results: $RESULTS_DIR"

# --- Execute ---
case "$SESSION" in
    control)
        run_control
        echo ""
        echo "=== Control session complete ==="
        echo "Run treatment: ./bench/run.sh $RUN_ID treatment"
        ;;
    treatment)
        run_treatment
        echo ""
        echo "=== Treatment session complete ==="
        echo "Score with: ./bench/score-v2.sh $RUN_ID"
        ;;
    both)
        run_control
        run_treatment
        echo ""
        echo "=== Run $RUN_ID Complete ==="
        echo "Score with: ./bench/score-v2.sh $RUN_ID"
        ;;
esac
