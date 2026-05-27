#!/usr/bin/env bash
set -euo pipefail

# MCP Effectiveness Benchmark: A/B test for MCP-based guide delivery
# Usage:
#   ./bench/run-mcp.sh <run_id> control    — Run without MCP (baseline)
#   ./bench/run-mcp.sh <run_id> treatment  — Run with MCP guide tools
#   ./bench/run-mcp.sh <run_id> both       — Run control then treatment
#
# Environment:
#   MODEL=claude-opus-4-7  ./bench/run-mcp.sh ...   — Override model (default: no flag = user default)

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="$HOME/claude_workspace"
RUN_ID="${1:?Usage: $0 <run_id> <control|treatment|both>}"
SESSION="${2:?Usage: $0 <run_id> <control|treatment|both>}"
RESULTS_DIR="$REPO_DIR/results/run-${RUN_ID}"
BUDGET="2.00"
MODEL="${MODEL:-}"

PROMPT_CONTROL="$REPO_DIR/bench/prompt-v3.txt"
PROMPT_TREATMENT="$REPO_DIR/bench/prompt-v3-mcp.txt"
MCP_CONFIG="$REPO_DIR/bench/mcp-config.json"

GEN_SRC="$WORKSPACE/src"
GEN_PYPROJECT="$WORKSPACE/pyproject.toml"

MCP_TOOL_PREFIX="mcp__mpg__"

# --- Workspace cleanup (same as run.sh) ---
cleanup_generated() {
    local dest="$1"
    mkdir -p "$dest"

    if [ -d "$GEN_SRC" ]; then
        mv "$GEN_SRC" "$dest/src"
        [ -f "$GEN_PYPROJECT" ] && mv "$GEN_PYPROJECT" "$dest/pyproject.toml"
    else
        local found_dir
        found_dir=$(find "$WORKSPACE" -maxdepth 2 -name "app.py" -path "*/src/app.py" \
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

    local sweep_dir="$dest/extra"
    for f in "$WORKSPACE"/__init__.py "$WORKSPACE"/README.md "$WORKSPACE"/requirements.txt \
             "$WORKSPACE"/setup.py "$WORKSPACE"/setup.cfg; do
        if [ -f "$f" ] && [ "$f" -nt "$RESULTS_DIR" ]; then
            mkdir -p "$sweep_dir"
            mv "$f" "$sweep_dir/"
            echo "[sweep] Captured extra file: $(basename "$f")"
        fi
    done

    [ -f "$GEN_PYPROJECT" ] && mv "$GEN_PYPROJECT" "$dest/pyproject.toml" 2>/dev/null || true
}

# --- JSONL verification ---
verify_jsonl() {
    local session_id="$1"
    local expected_mcp="$2"  # "yes" or "no"
    local verify_log="$RESULTS_DIR/mcp-verify.log"

    echo "=== JSONL Verification (session=$session_id, expect_mcp=$expected_mcp) ===" >> "$verify_log"

    # Find JSONL file
    local jsonl_path
    jsonl_path=$(find "$HOME/.claude/projects" -name "${session_id}.jsonl" 2>/dev/null | head -1)

    if [ -z "$jsonl_path" ]; then
        echo "JSONL: NOT FOUND" >> "$verify_log"
        echo "VERDICT: INVALID_ERROR (no JSONL)" >> "$verify_log"
        echo "INVALID_ERROR"
        return
    fi

    echo "JSONL: $jsonl_path" >> "$verify_log"

    # Count MCP tool calls
    local search_count retrieve_count tool_count
    search_count=$(grep -o "\"${MCP_TOOL_PREFIX}search_guides\"" "$jsonl_path" 2>/dev/null | wc -l | tr -d ' ')
    retrieve_count=$(grep -o "\"${MCP_TOOL_PREFIX}retrieve_guides\"" "$jsonl_path" 2>/dev/null | wc -l | tr -d ' ')
    tool_count=$(grep -o "\"${MCP_TOOL_PREFIX}" "$jsonl_path" 2>/dev/null | wc -l | tr -d ' ')

    echo "search_guides mentions: $search_count" >> "$verify_log"
    echo "retrieve_guides mentions: $retrieve_count" >> "$verify_log"
    echo "total mcp__mpg__ mentions: $tool_count" >> "$verify_log"

    # Check tool registration
    local tools_registered
    tools_registered=$(python3 -c "
import json, sys
with open('$jsonl_path') as f:
    for line in f:
        d = json.loads(line.strip())
        att = d.get('attachment', {})
        if att.get('type') == 'deferred_tools_delta':
            added = att.get('addedNames', [])
            mcp = [t for t in added if '${MCP_TOOL_PREFIX}' in t]
            if mcp:
                print('yes')
                sys.exit(0)
print('no')
" 2>/dev/null)

    echo "tools_registered: $tools_registered" >> "$verify_log"

    # Check for actual tool_use blocks
    local tool_use_count
    tool_use_count=$(python3 -c "
import json
count = 0
with open('$jsonl_path') as f:
    for line in f:
        d = json.loads(line.strip())
        msg = d.get('message', {})
        for block in msg.get('content', []):
            if isinstance(block, dict) and block.get('type') == 'tool_use' and '${MCP_TOOL_PREFIX}' in block.get('name', ''):
                count += 1
print(count)
" 2>/dev/null)

    echo "tool_use blocks: $tool_use_count" >> "$verify_log"

    if [ "$expected_mcp" = "no" ]; then
        if [ "$tool_use_count" -eq 0 ]; then
            echo "VERDICT: VALID (control, 0 MCP calls)" >> "$verify_log"
            echo "VALID"
        else
            echo "VERDICT: INVALID_ERROR (control had $tool_use_count MCP calls)" >> "$verify_log"
            echo "INVALID_ERROR"
        fi
    else
        if [ "$tools_registered" = "no" ]; then
            echo "VERDICT: INVALID_ERROR (MCP tools never registered)" >> "$verify_log"
            echo "INVALID_ERROR"
        elif [ "$tool_use_count" -eq 0 ]; then
            echo "VERDICT: INVALID_NO_TOOL (tools registered but never called)" >> "$verify_log"
            echo "INVALID_NO_TOOL"
        elif [ "$search_count" -eq 0 ] || [ "$retrieve_count" -eq 0 ]; then
            echo "VERDICT: INVALID_NO_TOOL (missing search=$search_count or retrieve=$retrieve_count)" >> "$verify_log"
            echo "INVALID_NO_TOOL"
        elif [ "$search_count" -lt 2 ] || [ "$retrieve_count" -lt 2 ]; then
            echo "VERDICT: VALID (but low coverage: search=$search_count, retrieve=$retrieve_count)" >> "$verify_log"
            echo "VALID"
        else
            echo "VERDICT: VALID (search=$search_count, retrieve=$retrieve_count)" >> "$verify_log"
            echo "VALID"
        fi
    fi

    echo "" >> "$verify_log"
}

# --- Session runners ---
run_control() {
    echo ""
    echo "--- Session A: Control (MCP DISABLED) ---"

    if [ -d "$GEN_SRC" ]; then
        BACKUP="$WORKSPACE/src.__bench_backup_$(date +%s)__"
        echo "[warning] Existing $GEN_SRC found. Moving to $BACKUP"
        mv "$GEN_SRC" "$BACKUP"
    fi

    echo "[running] claude -p (Control, no MCP${MODEL:+, model=$MODEL}) from $WORKSPACE ..."
    local session_json
    session_json=$(cd "$WORKSPACE" && claude -p \
        ${MODEL:+--model "$MODEL"} \
        --strict-mcp-config --mcp-config '{"mcpServers":{}}' \
        --output-format json --max-budget-usd "$BUDGET" \
        < "$PROMPT_CONTROL" 2>"$RESULTS_DIR/session-a.stderr") || true

    echo "$session_json" > "$RESULTS_DIR/session-a.json"

    local session_id
    session_id=$(python3 -c "import json; print(json.load(open('$RESULTS_DIR/session-a.json')).get('session_id',''))" 2>/dev/null || echo "")

    echo "[info] Control session_id: $session_id"

    cleanup_generated "$RESULTS_DIR/control"
    echo "[ok] Control files saved to $RESULTS_DIR/control/"

    if [ -n "$session_id" ]; then
        local verdict
        verdict=$(verify_jsonl "$session_id" "no")
        echo "[verify] Control verdict: $verdict"
    else
        echo "[verify] Control verdict: INVALID_ERROR (no session_id)"
    fi
}

run_treatment() {
    echo ""
    echo "--- Session B: Treatment (MCP ENABLED) ---"

    if [ -d "$GEN_SRC" ]; then
        BACKUP="$WORKSPACE/src.__bench_backup_$(date +%s)__"
        echo "[warning] Existing $GEN_SRC found. Moving to $BACKUP"
        mv "$GEN_SRC" "$BACKUP"
    fi

    echo "[running] claude -p (Treatment, MCP enabled${MODEL:+, model=$MODEL}) from $WORKSPACE ..."
    local session_json
    session_json=$(cd "$WORKSPACE" && claude -p \
        ${MODEL:+--model "$MODEL"} \
        --strict-mcp-config --mcp-config "$MCP_CONFIG" \
        --allowedTools \
            'Bash(*)' 'Read(*)' 'Write(*)' 'Edit(*)' \
            'mcp__mpg__search_guides' \
            'mcp__mpg__retrieve_guides' \
            'mcp__mpg__list_guides' \
            'mcp__mpg__detect_python_version' \
        --output-format json --max-budget-usd "$BUDGET" \
        < "$PROMPT_TREATMENT" 2>"$RESULTS_DIR/session-b.stderr") || true

    echo "$session_json" > "$RESULTS_DIR/session-b.json"

    local session_id
    session_id=$(python3 -c "import json; print(json.load(open('$RESULTS_DIR/session-b.json')).get('session_id',''))" 2>/dev/null || echo "")

    echo "[info] Treatment session_id: $session_id"

    cleanup_generated "$RESULTS_DIR/treatment"
    echo "[ok] Treatment files saved to $RESULTS_DIR/treatment/"

    if [ -n "$session_id" ]; then
        local verdict
        verdict=$(verify_jsonl "$session_id" "yes")
        echo "[verify] Treatment verdict: $verdict"
    else
        echo "[verify] Treatment verdict: INVALID_ERROR (no session_id)"
    fi
}

# --- Pre-flight checks ---
echo "=== Pre-flight checks ==="

if [ ! -f "$PROMPT_CONTROL" ]; then
    echo "ERROR: Control prompt not found at $PROMPT_CONTROL" >&2
    exit 1
fi

if [ ! -f "$PROMPT_TREATMENT" ]; then
    echo "ERROR: Treatment prompt not found at $PROMPT_TREATMENT" >&2
    exit 1
fi

if [ ! -f "$MCP_CONFIG" ]; then
    echo "ERROR: MCP config not found at $MCP_CONFIG" >&2
    exit 1
fi

# Check for stale rules guidance that would contaminate the A/B test
RULES_GUIDANCE="$WORKSPACE/.claude/rules/modern-python.md"
if [ -f "$RULES_GUIDANCE" ]; then
    echo "ERROR: Stale rules file found at $RULES_GUIDANCE" >&2
    echo "  This would contaminate Control. Remove it first: rm $RULES_GUIDANCE" >&2
    exit 1
fi
echo "[ok] No stale rules guidance"

# Verify mpg is installed
if ! command -v mpg &>/dev/null; then
    echo "ERROR: mpg command not found. Install: uv tool install modern-python-guidance" >&2
    exit 1
fi
echo "[ok] mpg $(mpg --version)"

# Verify MCP server responds
echo -n "[check] MCP server startup test... "
mcp_test_result=$(echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}},"id":1}' | mpg mcp 2>/dev/null | head -1)
if echo "$mcp_test_result" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['result']['serverInfo']['name']=='modern-python-guidance'" 2>/dev/null; then
    echo "ok"
else
    echo "FAILED"
    echo "ERROR: MCP server did not respond correctly" >&2
    echo "Response: $mcp_test_result" >&2
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

echo ""
echo "=== MCP Effectiveness Benchmark Run $RUN_ID ($SESSION) ==="
echo "Control prompt: $PROMPT_CONTROL"
echo "Treatment prompt: $PROMPT_TREATMENT"
echo "MCP config: $MCP_CONFIG"
echo "Model: ${MODEL:-<default>}"
echo "Results: $RESULTS_DIR"

# --- Execute ---
case "$SESSION" in
    control)
        run_control
        echo ""
        echo "=== Control session complete ==="
        echo "Run treatment: ./bench/run-mcp.sh $RUN_ID treatment"
        ;;
    treatment)
        run_treatment
        echo ""
        echo "=== Treatment session complete ==="
        echo "Score with: ./bench/score-v3.sh $RUN_ID"
        ;;
    both)
        run_control
        run_treatment
        echo ""
        echo "=== Run $RUN_ID Complete ==="
        echo "Score with: ./bench/score-v3.sh $RUN_ID"
        ;;
esac
