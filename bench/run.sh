#!/usr/bin/env bash
set -euo pipefail

# Effectiveness Benchmark: A/B test for SKILL.md pre-generation guidance
# Usage: ./bench/run.sh [run_id]
#   run_id: integer (default: 1). Results go to results/run-<run_id>/

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$HOME/claude_workspace"
SKILL_DIR="$HOME/.claude/skills/modern-python-guidance"
SKILL_DISABLED="${SKILL_DIR}.__disabled__"
RUN_ID="${1:-1}"
RESULTS_DIR="$REPO_DIR/results/run-${RUN_ID}"
PROMPT_FILE="$REPO_DIR/bench/prompt.txt"
BUDGET="2.00"

# Generated file paths (CC writes to ~/claude_workspace/)
GEN_SRC="$WORKSPACE/src"
GEN_PYPROJECT="$WORKSPACE/pyproject.toml"

cleanup_skill() {
    if [ -d "$SKILL_DISABLED" ]; then
        mv "$SKILL_DISABLED" "$SKILL_DIR"
        echo "[cleanup] Skill restored."
    fi
}

cleanup_generated() {
    local dest="$1"
    mkdir -p "$dest"
    [ -d "$GEN_SRC" ] && mv "$GEN_SRC" "$dest/src"
    [ -f "$GEN_PYPROJECT" ] && mv "$GEN_PYPROJECT" "$dest/pyproject.toml"
}

echo "=== Effectiveness Benchmark Run $RUN_ID ==="
echo "Prompt: $PROMPT_FILE"
echo "Results: $RESULTS_DIR"
echo ""

# Pre-flight checks
if [ ! -f "$PROMPT_FILE" ]; then
    echo "ERROR: prompt.txt not found at $PROMPT_FILE" >&2
    exit 1
fi

if [ ! -d "$SKILL_DIR" ]; then
    echo "ERROR: Skill not found at $SKILL_DIR" >&2
    echo "Symlink it first: ln -s $REPO_DIR ~/.claude/skills/modern-python-guidance" >&2
    exit 1
fi

if [ -d "$RESULTS_DIR" ]; then
    echo "ERROR: Results directory already exists: $RESULTS_DIR" >&2
    echo "Remove it or use a different run_id." >&2
    exit 1
fi

# Back up existing generated files if present
if [ -d "$GEN_SRC" ]; then
    BACKUP="$WORKSPACE/src.__bench_backup_$(date +%s)__"
    echo "[warning] Existing $GEN_SRC found. Moving to $BACKUP"
    mv "$GEN_SRC" "$BACKUP"
fi

mkdir -p "$RESULTS_DIR"

# === Session A: Control (no skill) ===
echo ""
echo "--- Session A: Control (skill DISABLED) ---"

# Disable skill
mv "$SKILL_DIR" "$SKILL_DISABLED"
trap cleanup_skill EXIT

# Verify skill is gone
if [ -d "$SKILL_DIR" ]; then
    echo "ERROR: Skill still exists after mv!" >&2
    exit 1
fi
echo "[ok] Skill disabled: $(ls -d "$SKILL_DISABLED")"

# Run CC in pipe mode
echo "[running] claude -p (Control)..."
claude -p --output-format json --max-budget-usd "$BUDGET" \
    < "$PROMPT_FILE" > "$RESULTS_DIR/session-a.json" 2>"$RESULTS_DIR/session-a.stderr" || true

# Capture generated files
cleanup_generated "$RESULTS_DIR/control"
echo "[ok] Control files saved to $RESULTS_DIR/control/"

# === Session B: Treatment (with skill) ===
echo ""
echo "--- Session B: Treatment (skill ENABLED) ---"

# Restore skill
mv "$SKILL_DISABLED" "$SKILL_DIR"
trap - EXIT

# Verify skill is back
if [ ! -d "$SKILL_DIR" ]; then
    echo "ERROR: Skill not restored!" >&2
    exit 1
fi
echo "[ok] Skill enabled: $(ls -d "$SKILL_DIR")"

# Run CC in pipe mode
echo "[running] claude -p (Treatment)..."
claude -p --output-format json --max-budget-usd "$BUDGET" \
    < "$PROMPT_FILE" > "$RESULTS_DIR/session-b.json" 2>"$RESULTS_DIR/session-b.stderr" || true

# Capture generated files
cleanup_generated "$RESULTS_DIR/treatment"
echo "[ok] Treatment files saved to $RESULTS_DIR/treatment/"

echo ""
echo "=== Run $RUN_ID Complete ==="
echo "Score with: ./bench/score.sh $RUN_ID"
