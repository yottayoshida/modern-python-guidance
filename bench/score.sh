#!/usr/bin/env bash
set -euo pipefail

# Automated scorer for effectiveness benchmark
# Usage: ./bench/score.sh [run_id]

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ID="${1:-1}"
RESULTS_DIR="$REPO_DIR/results/run-${RUN_ID}"

if [ ! -d "$RESULTS_DIR" ]; then
    echo "ERROR: Results not found: $RESULTS_DIR" >&2
    echo "Run the benchmark first: ./bench/run.sh $RUN_ID" >&2
    exit 1
fi

score_session() {
    local session_name="$1"   # "control" or "treatment"
    local src_dir="$RESULTS_DIR/$session_name/src"
    local modern=0
    local outdated=0
    local total=17
    local details=""

    if [ ! -d "$src_dir" ]; then
        echo "  [ERROR] $src_dir not found"
        return
    fi

    # --- P-01: Pydantic model (6 items) ---
    local models="$src_dir/models.py"
    if [ -f "$models" ]; then
        # P-01-1: @validator → @field_validator
        if grep -q '@field_validator' "$models"; then
            modern=$((modern + 1)); details+="  P-01-1: MODERN (@field_validator)\n"
        elif grep -q '@validator' "$models"; then
            outdated=$((outdated + 1)); details+="  P-01-1: OUTDATED (@validator)\n"
        else
            details+="  P-01-1: NOT FOUND (no validator decorator)\n"
        fi

        # P-01-2: @root_validator → @model_validator
        if grep -q '@model_validator' "$models"; then
            modern=$((modern + 1)); details+="  P-01-2: MODERN (@model_validator)\n"
        elif grep -q '@root_validator' "$models"; then
            outdated=$((outdated + 1)); details+="  P-01-2: OUTDATED (@root_validator)\n"
        else
            # Not all implementations use root validators — count as modern (not required)
            modern=$((modern + 1)); details+="  P-01-2: MODERN (no root_validator needed)\n"
        fi

        # P-01-3: class Config → model_config = ConfigDict(...)
        if grep -q 'model_config' "$models"; then
            modern=$((modern + 1)); details+="  P-01-3: MODERN (model_config)\n"
        elif grep -q 'class Config' "$models"; then
            outdated=$((outdated + 1)); details+="  P-01-3: OUTDATED (class Config)\n"
        else
            details+="  P-01-3: NOT FOUND\n"
        fi

        # P-01-4: orm_mode → from_attributes
        if grep -q 'from_attributes' "$models"; then
            modern=$((modern + 1)); details+="  P-01-4: MODERN (from_attributes)\n"
        elif grep -q 'orm_mode' "$models"; then
            outdated=$((outdated + 1)); details+="  P-01-4: OUTDATED (orm_mode)\n"
        else
            details+="  P-01-4: NOT FOUND\n"
        fi

        # P-01-5: allow_population_by_field_name → populate_by_name
        if grep -q 'populate_by_name' "$models"; then
            modern=$((modern + 1)); details+="  P-01-5: MODERN (populate_by_name)\n"
        elif grep -q 'allow_population_by_field_name' "$models"; then
            outdated=$((outdated + 1)); details+="  P-01-5: OUTDATED (allow_population_by_field_name)\n"
        else
            details+="  P-01-5: NOT FOUND\n"
        fi

        # P-01-6: .dict() → .model_dump()
        if grep -q '\.model_dump(' "$models"; then
            modern=$((modern + 1)); details+="  P-01-6: MODERN (.model_dump())\n"
        elif grep -q '\.dict(' "$models"; then
            outdated=$((outdated + 1)); details+="  P-01-6: OUTDATED (.dict())\n"
        else
            details+="  P-01-6: NOT FOUND\n"
        fi
    else
        details+="  P-01: MISSING (models.py not found)\n"
    fi

    # --- P-02: Pydantic serialization (5 items) ---
    local serial="$src_dir/serialization.py"
    if [ -f "$serial" ]; then
        # P-02-1: .parse_obj() → .model_validate()
        if grep -q '\.model_validate(' "$serial"; then
            modern=$((modern + 1)); details+="  P-02-1: MODERN (.model_validate())\n"
        elif grep -q '\.parse_obj(' "$serial"; then
            outdated=$((outdated + 1)); details+="  P-02-1: OUTDATED (.parse_obj())\n"
        else
            details+="  P-02-1: NOT FOUND\n"
        fi

        # P-02-2: .parse_raw() → .model_validate_json()
        if grep -q '\.model_validate_json(' "$serial"; then
            modern=$((modern + 1)); details+="  P-02-2: MODERN (.model_validate_json())\n"
        elif grep -q '\.parse_raw(' "$serial"; then
            outdated=$((outdated + 1)); details+="  P-02-2: OUTDATED (.parse_raw())\n"
        else
            details+="  P-02-2: NOT FOUND\n"
        fi

        # P-02-3: .json() → .model_dump_json()
        if grep -q '\.model_dump_json(' "$serial"; then
            modern=$((modern + 1)); details+="  P-02-3: MODERN (.model_dump_json())\n"
        elif grep -q '\.json()' "$serial"; then
            outdated=$((outdated + 1)); details+="  P-02-3: OUTDATED (.json())\n"
        else
            details+="  P-02-3: NOT FOUND\n"
        fi

        # P-02-4: .schema() → .model_json_schema()
        if grep -q '\.model_json_schema(' "$serial"; then
            modern=$((modern + 1)); details+="  P-02-4: MODERN (.model_json_schema())\n"
        elif grep -q '\.schema(' "$serial"; then
            outdated=$((outdated + 1)); details+="  P-02-4: OUTDATED (.schema())\n"
        else
            details+="  P-02-4: NOT FOUND\n"
        fi

        # P-02-5: .copy() → .model_copy()
        if grep -q '\.model_copy(' "$serial"; then
            modern=$((modern + 1)); details+="  P-02-5: MODERN (.model_copy())\n"
        elif grep -q '\.copy(' "$serial"; then
            outdated=$((outdated + 1)); details+="  P-02-5: OUTDATED (.copy())\n"
        else
            details+="  P-02-5: NOT FOUND\n"
        fi
    else
        details+="  P-02: MISSING (serialization.py not found)\n"
    fi

    # --- P-03: FastAPI (3 items) ---
    local app="$src_dir/app.py"
    if [ -f "$app" ]; then
        # P-03-1 + P-03-2: on_event → lifespan
        if grep -q 'lifespan' "$app"; then
            modern=$((modern + 2)); details+="  P-03-1/2: MODERN (lifespan context manager)\n"
        elif grep -q 'on_event' "$app"; then
            outdated=$((outdated + 2)); details+="  P-03-1/2: OUTDATED (@app.on_event)\n"
        else
            details+="  P-03-1/2: NOT FOUND\n"
        fi

        # P-03-3: Depends without Annotated → Annotated[..., Depends()]
        if grep -q 'Annotated\[' "$app"; then
            modern=$((modern + 1)); details+="  P-03-3: MODERN (Annotated[..., Depends()])\n"
        elif grep -q 'Depends(' "$app"; then
            outdated=$((outdated + 1)); details+="  P-03-3: OUTDATED (Depends without Annotated)\n"
        else
            details+="  P-03-3: NOT FOUND\n"
        fi
    else
        details+="  P-03: MISSING (app.py not found)\n"
    fi

    # --- P-04: Async (2 items) ---
    local fetcher="$src_dir/fetcher.py"
    if [ -f "$fetcher" ]; then
        # P-04-1: per-request client → shared AsyncClient
        # Heuristic: if AsyncClient is created outside the fetch function, it's shared
        if grep -q 'AsyncClient' "$fetcher"; then
            modern=$((modern + 1)); details+="  P-04-1: MODERN (AsyncClient present)\n"
        else
            outdated=$((outdated + 1)); details+="  P-04-1: OUTDATED (no AsyncClient)\n"
        fi

        # P-04-2: asyncio.gather() → TaskGroup
        if grep -q 'TaskGroup' "$fetcher"; then
            modern=$((modern + 1)); details+="  P-04-2: MODERN (TaskGroup)\n"
        elif grep -q 'gather' "$fetcher"; then
            outdated=$((outdated + 1)); details+="  P-04-2: OUTDATED (asyncio.gather)\n"
        else
            details+="  P-04-2: NOT FOUND\n"
        fi
    else
        details+="  P-04: MISSING (fetcher.py not found)\n"
    fi

    # --- P-05: Subprocess (1 item — P-05-1 excluded) ---
    local runner="$src_dir/runner.py"
    if [ -f "$runner" ]; then
        # P-05-2: shell=True with f-string → list form
        if grep -q 'shell=True' "$runner"; then
            outdated=$((outdated + 1)); details+="  P-05-2: OUTDATED (shell=True)\n"
        elif grep -qE 'subprocess\.run\(\[' "$runner"; then
            modern=$((modern + 1)); details+="  P-05-2: MODERN (list form subprocess)\n"
        else
            # Default: if subprocess.run exists without shell=True, assume list form
            if grep -q 'subprocess' "$runner"; then
                modern=$((modern + 1)); details+="  P-05-2: MODERN (subprocess without shell=True)\n"
            else
                details+="  P-05-2: NOT FOUND\n"
            fi
        fi
    else
        details+="  P-05: MISSING (runner.py not found)\n"
    fi

    local score
    if [ "$total" -gt 0 ]; then
        score=$(echo "scale=1; $modern * 100 / $total" | bc)
    else
        score="0"
    fi

    echo "  Modern: $modern / $total ($score%)"
    echo "  Outdated: $outdated"
    echo "  Unscored: $((total - modern - outdated))"
    echo ""
    echo -e "$details"
}

verify_skill_load() {
    echo "=== Skill Load Verification ==="
    local json_a="$RESULTS_DIR/session-a.json"
    local json_b="$RESULTS_DIR/session-b.json"

    if [ ! -f "$json_a" ] || [ ! -f "$json_b" ]; then
        echo "  [SKIP] Session JSON files not found."
        return
    fi

    local tokens_a tokens_b
    tokens_a=$(python3 -c "
import json, sys
with open('$json_a') as f:
    d = json.load(f)
u = d.get('usage', {})
print(u.get('cache_creation_input_tokens', 0))
" 2>/dev/null || echo "N/A")

    tokens_b=$(python3 -c "
import json, sys
with open('$json_b') as f:
    d = json.load(f)
u = d.get('usage', {})
print(u.get('cache_creation_input_tokens', 0))
" 2>/dev/null || echo "N/A")

    echo "  Control (A) cache_creation_input_tokens: $tokens_a"
    echo "  Treatment (B) cache_creation_input_tokens: $tokens_b"

    if [ "$tokens_a" != "N/A" ] && [ "$tokens_b" != "N/A" ]; then
        local diff=$((tokens_b - tokens_a))
        echo "  Difference (B - A): $diff tokens"
        if [ "$diff" -gt 500 ]; then
            echo "  [PASS] Skill likely loaded (diff > 500 tokens)"
        else
            echo "  [WARN] Skill may NOT have loaded (diff <= 500 tokens)"
        fi
    fi
    echo ""
}

echo "=== Effectiveness Benchmark Scoring: Run $RUN_ID ==="
echo ""

echo "--- Control (A: no skill) ---"
score_session "control"

echo "--- Treatment (B: with skill) ---"
score_session "treatment"

verify_skill_load
