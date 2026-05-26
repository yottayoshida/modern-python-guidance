#!/usr/bin/env bash
set -euo pipefail

# Effectiveness Benchmark: A/B test for SKILL.md pre-generation guidance
# Usage:
#   ./bench/run.sh <run_id> control    — Run Session A (skill disabled)
#   ./bench/run.sh <run_id> treatment  — Run Session B (skill enabled)
#   ./bench/run.sh <run_id> both       — Run A then B sequentially

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$HOME/claude_workspace"
SKILL_DIR="$WORKSPACE/.claude/skills/modern-python-guidance"
SKILL_TARGET="$REPO_DIR/skills/modern-python-guidance"
USER_SKILL_DIR="$HOME/.claude/skills/modern-python-guidance"
RUN_ID="${1:?Usage: $0 <run_id> <control|treatment|both>}"
SESSION="${2:?Usage: $0 <run_id> <control|treatment|both>}"
RESULTS_DIR="$REPO_DIR/results/run-${RUN_ID}"
PROMPT_FILE="$REPO_DIR/bench/prompt.txt"
BUDGET="2.00"

GEN_SRC="$WORKSPACE/src"
GEN_PYPROJECT="$WORKSPACE/pyproject.toml"

# --- Skill toggle: rm/ln-s (not mv) ---
# CC scans .claude/skills/*/SKILL.md regardless of directory name.
# Renaming within .claude/skills/ does NOT disable the skill.
# The only reliable method: remove the symlink entirely.

disable_skill() {
    if [ -L "$SKILL_DIR" ] || [ -d "$SKILL_DIR" ]; then
        rm "$SKILL_DIR"
    fi
}

enable_skill() {
    if [ ! -L "$SKILL_DIR" ] && [ ! -d "$SKILL_DIR" ]; then
        ln -s "$SKILL_TARGET" "$SKILL_DIR"
    fi
}

restore_skill_on_exit() {
    enable_skill
    echo "[cleanup] Skill restored."
}

# --- Verification logging ---
record_verify() {
    local label="$1"
    local log="$RESULTS_DIR/skill-verify.log"

    echo "=== $label $(date -u '+%Y-%m-%dT%H:%M:%SZ') ===" >> "$log"

    # Target skill state
    echo "SKILL_DIR=$SKILL_DIR" >> "$log"
    if [ -L "$SKILL_DIR" ]; then
        echo "status: PRESENT (symlink -> $(readlink "$SKILL_DIR"))" >> "$log"
    elif [ -d "$SKILL_DIR" ]; then
        echo "status: PRESENT (directory)" >> "$log"
    else
        echo "status: ABSENT" >> "$log"
    fi

    # User-level skill check
    if [ -L "$USER_SKILL_DIR" ] || [ -d "$USER_SKILL_DIR" ]; then
        echo "WARNING: user-level skill also exists at $USER_SKILL_DIR" >> "$log"
    else
        echo "user-level: absent (ok)" >> "$log"
    fi

    # Full skill directory listing (catch unexpected skills)
    echo "--- all project-level skills ---" >> "$log"
    ls "$WORKSPACE/.claude/skills/" 2>/dev/null | grep -v '^\.' >> "$log" || echo "(empty)" >> "$log"

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
    echo "--- Session A: Control (skill DISABLED) ---"

    # Disable: remove symlink entirely
    disable_skill
    trap restore_skill_on_exit EXIT

    # Verify skill is gone
    if [ -L "$SKILL_DIR" ] || [ -d "$SKILL_DIR" ]; then
        echo "ERROR: Skill still exists after rm!" >&2
        exit 1
    fi
    record_verify "PRE-CONTROL"
    echo "[ok] Skill removed from .claude/skills/ (verified)"

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

    # Restore skill if running control only
    if [ "$SESSION" = "control" ]; then
        enable_skill
        trap - EXIT
        echo "[ok] Skill symlink restored."
    fi
}

run_treatment() {
    echo ""
    echo "--- Session B: Treatment (skill ENABLED) ---"

    # Ensure skill is present
    enable_skill
    trap - EXIT

    if [ ! -L "$SKILL_DIR" ] && [ ! -d "$SKILL_DIR" ]; then
        echo "ERROR: Skill not found at $SKILL_DIR" >&2
        exit 1
    fi
    record_verify "PRE-TREATMENT"
    echo "[ok] Skill present in .claude/skills/ (verified)"

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

if [ ! -d "$SKILL_TARGET" ]; then
    echo "ERROR: Skill source not found at $SKILL_TARGET" >&2
    exit 1
fi

if [ ! -L "$SKILL_DIR" ] && [ ! -d "$SKILL_DIR" ]; then
    echo "ERROR: Skill not symlinked at $SKILL_DIR" >&2
    echo "Create it: ln -s $SKILL_TARGET $SKILL_DIR" >&2
    exit 1
fi

# Check user-level duplicate
if [ -L "$USER_SKILL_DIR" ] || [ -d "$USER_SKILL_DIR" ]; then
    echo "ERROR: Skill also exists at user-level $USER_SKILL_DIR" >&2
    echo "Remove it to avoid contamination: rm $USER_SKILL_DIR" >&2
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
        echo "Score with: ./bench/score.sh $RUN_ID"
        ;;
    both)
        run_control
        run_treatment
        echo ""
        echo "=== Run $RUN_ID Complete ==="
        echo "Score with: ./bench/score.sh $RUN_ID"
        ;;
esac
