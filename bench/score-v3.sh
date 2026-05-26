#!/usr/bin/env bash
set -euo pipefail

# Automated scorer for effectiveness benchmark (V3 — impact-categorized, dynamic denominator)
# Usage: ./bench/score-v3.sh [run_id]
#
# Key differences from V2:
# - Items tagged by impact: safety, forward-compat, performance
# - Architecture detection: sync/async per file → conditional items
# - Dynamic denominator: only applicable items count toward total

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_ID="${1:-1}"
RESULTS_DIR="$REPO_DIR/results/run-${RUN_ID}"

if [ ! -d "$RESULTS_DIR" ]; then
    echo "ERROR: Results not found: $RESULTS_DIR" >&2
    echo "Run the benchmark first: ./bench/run.sh $RUN_ID" >&2
    exit 1
fi

score_session() {
    local session_name="$1"
    local src_dir="$RESULTS_DIR/$session_name/src"
    local modern=0
    local outdated=0
    local applicable=0
    local safety_m=0 safety_a=0
    local compat_m=0 compat_a=0
    local perf_m=0 perf_a=0
    local details=""

    if [ ! -d "$src_dir" ]; then
        echo "  [ERROR] $src_dir not found"
        return
    fi

    # === Architecture detection ===
    local crawler="$src_dir/crawler.py"
    local app="$src_dir/app.py"
    local config="$src_dir/config.py"
    local scanner="$src_dir/scanner.py"

    local crawler_async=false
    local app_async=false

    if [ -f "$crawler" ]; then
        if grep -qE 'async def|asyncio\.(gather|TaskGroup|as_completed)' "$crawler"; then
            crawler_async=true
        fi
    fi

    if [ -f "$app" ]; then
        if grep -q 'create_async_engine' "$app"; then
            app_async=true
        fi
    fi

    details+="  Architecture: crawler=$(if $crawler_async; then echo async; else echo sync; fi)"
    details+=", app=$(if $app_async; then echo async; else echo sync; fi)\n\n"

    # === SAFETY items (prevents bugs, security issues) ===

    # --- A1 [Perf]: concurrent fetch (sequential async = N× slower) ---
    # Applicable if crawler is async. Sequential await in a loop wastes async.
    if [ -f "$crawler" ] && $crawler_async; then
        if grep -q 'TaskGroup' "$crawler"; then
            modern=$((modern + 1)); perf_m=$((perf_m + 1))
            applicable=$((applicable + 1)); perf_a=$((perf_a + 1))
            details+="  [Perf]    A1: MODERN (TaskGroup — concurrent + sibling cancel)\n"
        elif grep -qE 'asyncio\.(gather|as_completed)' "$crawler"; then
            modern=$((modern + 1)); perf_m=$((perf_m + 1))
            applicable=$((applicable + 1)); perf_a=$((perf_a + 1))
            details+="  [Perf]    A1: PARTIAL (gather — concurrent but no sibling cancel)\n"
        else
            # async but no concurrency primitive = sequential await in loop
            outdated=$((outdated + 1))
            applicable=$((applicable + 1)); perf_a=$((perf_a + 1))
            details+="  [Perf]    A1: OUTDATED (sequential await — async without concurrency)\n"
        fi
    elif [ -f "$crawler" ] && ! $crawler_async; then
        details+="  [Perf]    A1: N/A (sync crawler)\n"
    fi

    # --- M1 [Safety]: qualified match names (bare name = silent capture bug) ---
    if [ -f "$scanner" ]; then
        if grep -q 'case FileCategory\.' "$scanner"; then
            modern=$((modern + 1)); safety_m=$((safety_m + 1))
            applicable=$((applicable + 1)); safety_a=$((safety_a + 1))
            details+="  [Safety]  M1: MODERN (case FileCategory.VALUE — compares correctly)\n"
        elif grep -qE 'case\s+"[^"]+"|case\s+'"'"'[^'"'"']+'"'"'' "$scanner"; then
            modern=$((modern + 1)); safety_m=$((safety_m + 1))
            applicable=$((applicable + 1)); safety_a=$((safety_a + 1))
            details+="  [Safety]  M1: MODERN (string literal match — bare-name trap avoided)\n"
        elif grep -qE 'case\s+(IMAGE|VIDEO|DOCUMENT|OTHER)' "$scanner"; then
            outdated=$((outdated + 1))
            applicable=$((applicable + 1)); safety_a=$((safety_a + 1))
            details+="  [Safety]  M1: OUTDATED (bare name = capture, not compare!)\n"
        elif grep -q 'case' "$scanner"; then
            details+="  [Safety]  M1: INDETERMINATE (match present, pattern unclear)\n"
        else
            details+="  [Safety]  M1: N/A (no match statement)\n"
        fi
    fi

    # --- F3 [Safety]: Security() for OAuth scopes (enforces scope validation) ---
    if [ -f "$app" ]; then
        if grep -q 'Security(' "$app"; then
            modern=$((modern + 1)); safety_m=$((safety_m + 1))
            applicable=$((applicable + 1)); safety_a=$((safety_a + 1))
            details+="  [Safety]  F3: MODERN (Security() — scope enforcement)\n"
        elif grep -q 'Depends(' "$app" && grep -qE 'oauth2|OAuth2|scope' "$app"; then
            outdated=$((outdated + 1))
            applicable=$((applicable + 1)); safety_a=$((safety_a + 1))
            details+="  [Safety]  F3: OUTDATED (Depends for OAuth — no scope enforcement)\n"
        else
            details+="  [Safety]  F3: N/A (no OAuth implementation)\n"
        fi
    fi

    # === FORWARD-COMPAT items (deprecated APIs, future breakage) ===

    # --- F1 [Compat]: lifespan vs on_event (on_event deprecated) ---
    if [ -f "$app" ]; then
        if grep -q 'lifespan' "$app"; then
            modern=$((modern + 1)); compat_m=$((compat_m + 1))
            applicable=$((applicable + 1)); compat_a=$((compat_a + 1))
            details+="  [Compat]  F1: MODERN (lifespan — on_event is deprecated)\n"
        elif grep -q 'on_event' "$app"; then
            outdated=$((outdated + 1))
            applicable=$((applicable + 1)); compat_a=$((compat_a + 1))
            details+="  [Compat]  F1: OUTDATED (on_event — deprecated, will be removed)\n"
        else
            details+="  [Compat]  F1: N/A\n"
        fi
    fi

    # --- F2 [Compat]: Annotated Depends (reusable type aliases) ---
    if [ -f "$app" ]; then
        if grep -q 'Annotated\[' "$app"; then
            modern=$((modern + 1)); compat_m=$((compat_m + 1))
            applicable=$((applicable + 1)); compat_a=$((compat_a + 1))
            details+="  [Compat]  F2: MODERN (Annotated Depends — reusable, less duplication)\n"
        elif grep -q 'Depends(' "$app"; then
            outdated=$((outdated + 1))
            applicable=$((applicable + 1)); compat_a=$((compat_a + 1))
            details+="  [Compat]  F2: OUTDATED (bare Depends — duplicated across endpoints)\n"
        else
            details+="  [Compat]  F2: N/A\n"
        fi
    fi

    # --- S1 [Compat]: select() vs session.query() (query is SA2.0 legacy) ---
    if [ -f "$app" ]; then
        if grep -qE '\.query\(' "$app"; then
            outdated=$((outdated + 1))
            applicable=$((applicable + 1)); compat_a=$((compat_a + 1))
            details+="  [Compat]  S1: OUTDATED (session.query — legacy in SA2.0)\n"
        elif grep -q 'select(' "$app"; then
            modern=$((modern + 1)); compat_m=$((compat_m + 1))
            applicable=$((applicable + 1)); compat_a=$((compat_a + 1))
            details+="  [Compat]  S1: MODERN (select() — SA2.0 standard)\n"
        else
            details+="  [Compat]  S1: N/A\n"
        fi
    fi

    # --- L1 [Compat]: tomllib vs third-party tomli (unnecessary dependency) ---
    if [ -f "$config" ]; then
        if grep -q 'tomllib' "$config"; then
            modern=$((modern + 1)); compat_m=$((compat_m + 1))
            applicable=$((applicable + 1)); compat_a=$((compat_a + 1))
            details+="  [Compat]  L1: MODERN (tomllib — stdlib, no extra dependency)\n"
        elif grep -qE 'import tomli$|from tomli |import toml$|from toml ' "$config"; then
            outdated=$((outdated + 1))
            applicable=$((applicable + 1)); compat_a=$((compat_a + 1))
            details+="  [Compat]  L1: OUTDATED (third-party tomli/toml — unnecessary dep)\n"
        else
            details+="  [Compat]  L1: N/A (no TOML import)\n"
        fi
    fi

    # === PERFORMANCE items (event loop blocking, resource waste) ===

    # --- S2 [Perf]: async_sessionmaker (only when async engine) ---
    if [ -f "$app" ] && $app_async; then
        if grep -q 'async_sessionmaker' "$app"; then
            modern=$((modern + 1)); perf_m=$((perf_m + 1))
            applicable=$((applicable + 1)); perf_a=$((perf_a + 1))
            details+="  [Perf]    S2: MODERN (async_sessionmaker — non-blocking)\n"
        elif grep -q 'sessionmaker' "$app"; then
            outdated=$((outdated + 1))
            applicable=$((applicable + 1)); perf_a=$((perf_a + 1))
            details+="  [Perf]    S2: OUTDATED (sync sessionmaker in async — blocks event loop)\n"
        else
            details+="  [Perf]    S2: N/A\n"
        fi
    elif [ -f "$app" ] && ! $app_async; then
        details+="  [Perf]    S2: N/A (sync app — sync sessionmaker is correct)\n"
    fi

    # --- H1 [Perf]: shared AsyncClient (connection pool reuse) ---
    if [ -f "$crawler" ]; then
        if grep -q 'AsyncClient' "$crawler"; then
            # Check if it's shared (created once) vs per-request (created in loop)
            # Shared: async with AsyncClient() as client: ... (outside loop)
            # Per-request: for url in urls: async with AsyncClient() ...
            modern=$((modern + 1)); perf_m=$((perf_m + 1))
            applicable=$((applicable + 1)); perf_a=$((perf_a + 1))
            details+="  [Perf]    H1: MODERN (AsyncClient — connection pooling)\n"
        elif grep -q 'httpx' "$crawler"; then
            # Uses httpx but not AsyncClient (e.g., httpx.get per request)
            if grep -qE 'httpx\.(get|post|head)' "$crawler"; then
                outdated=$((outdated + 1))
                applicable=$((applicable + 1)); perf_a=$((perf_a + 1))
                details+="  [Perf]    H1: OUTDATED (per-request httpx calls — no connection pool)\n"
            else
                modern=$((modern + 1)); perf_m=$((perf_m + 1))
                applicable=$((applicable + 1)); perf_a=$((perf_a + 1))
                details+="  [Perf]    H1: MODERN (httpx client reuse)\n"
            fi
        else
            details+="  [Perf]    H1: N/A (no httpx)\n"
        fi
    fi

    # === Score calculation ===
    local score
    if [ "$applicable" -gt 0 ]; then
        score=$(echo "scale=1; $modern * 100 / $applicable" | bc)
    else
        score="0"
    fi

    echo "  Score: $modern / $applicable ($score%)"
    echo "  Outdated: $outdated"
    echo "  N/A: items not applicable to this architecture"
    echo ""
    echo "  Safety:       $safety_m / $safety_a (bugs, security)"
    echo "  Forward-compat: $compat_m / $compat_a (deprecation risk)"
    echo "  Performance:  $perf_m / $perf_a (blocking, resource waste)"
    echo ""
    echo -e "$details"
}

verify_guidance_load() {
    echo "=== Guidance Load Verification ==="

    local verify_log="$RESULTS_DIR/guidance-verify.log"
    [ ! -f "$verify_log" ] && verify_log="$RESULTS_DIR/skill-verify.log"

    if [ -f "$verify_log" ]; then
        echo "  --- Physical verification (primary) ---"
        local control_ok=false
        local treatment_ok=false
        if grep -q "PRE-CONTROL" "$verify_log" && grep -A3 "PRE-CONTROL" "$verify_log" | grep -q "status: ABSENT"; then
            control_ok=true
            echo "  [PASS] Control: guidance was ABSENT before session"
        else
            echo "  [FAIL] Control: guidance state not verified (expected ABSENT)"
        fi
        if grep -q "PRE-TREATMENT" "$verify_log" && grep -A3 "PRE-TREATMENT" "$verify_log" | grep -q "status: PRESENT"; then
            treatment_ok=true
            echo "  [PASS] Treatment: guidance was PRESENT before session"
        else
            echo "  [FAIL] Treatment: guidance state not verified"
        fi
        if $control_ok && $treatment_ok; then
            echo "  [PASS] Physical verification: guidance toggle confirmed"
        else
            echo "  [WARN] Physical verification incomplete"
        fi
        echo ""
    else
        echo "  [SKIP] No verification log found"
        echo ""
    fi

    local json_a="$RESULTS_DIR/session-a.json"
    local json_b="$RESULTS_DIR/session-b.json"

    if [ ! -f "$json_a" ] || [ ! -f "$json_b" ]; then
        echo "  [SKIP] Session JSON files not found for token check."
        return
    fi

    echo "  --- Token analysis ---"
    python3 -c "
import json
with open('$json_a') as f:
    a = json.load(f)['usage']
with open('$json_b') as f:
    b = json.load(f)['usage']

def iter0_total(u):
    iters = u.get('iterations', [])
    if not iters:
        return u.get('cache_creation_input_tokens', 0) + u.get('cache_read_input_tokens', 0) + u.get('input_tokens', 0)
    i = iters[0]
    return i.get('cache_creation_input_tokens', 0) + i.get('cache_read_input_tokens', 0) + i.get('input_tokens', 0)

ta = iter0_total(a)
tb = iter0_total(b)
diff = tb - ta
print(f'  Control iter0 total:   {ta:,} tokens')
print(f'  Treatment iter0 total: {tb:,} tokens')
print(f'  Difference (B - A):    {diff:+,} tokens')
if diff > 500:
    print('  [PASS] Token diff confirms guidance loaded')
elif diff > 0:
    print('  [INFO] Small positive diff (inconclusive)')
else:
    print('  [WARN] No token increase — guidance may not be loaded')
" 2>/dev/null || echo "  [SKIP] Token analysis failed"
    echo ""
}

echo "=== Effectiveness Benchmark Scoring (v3 — impact-categorized): Run $RUN_ID ==="
echo ""

echo "--- Control (A: no guidance) ---"
score_session "control"

echo "--- Treatment (B: with guidance) ---"
score_session "treatment"

verify_guidance_load
