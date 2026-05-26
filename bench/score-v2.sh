#!/usr/bin/env bash
set -euo pipefail

# Automated scorer for effectiveness benchmark (V2 — 13 items)
# Usage: ./bench/score-v2.sh [run_id]

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
    local total=13
    local tier_e=0  # Embedded (max 4)
    local tier_g=0  # Guide-listed (max 4)
    local tier_u=0  # Uncovered (max 5)
    local details=""

    if [ ! -d "$src_dir" ]; then
        echo "  [ERROR] $src_dir not found"
        return
    fi

    # --- A1 [Tier E]: gather → TaskGroup (crawler.py) ---
    local crawler="$src_dir/crawler.py"
    if [ -f "$crawler" ]; then
        if grep -q 'TaskGroup' "$crawler"; then
            modern=$((modern + 1)); tier_e=$((tier_e + 1))
            details+="  [E] A1: MODERN (TaskGroup)\n"
        elif grep -q 'gather' "$crawler"; then
            outdated=$((outdated + 1))
            details+="  [E] A1: OUTDATED (asyncio.gather)\n"
        else
            details+="  [E] A1: NOT FOUND\n"
        fi

        # --- H1 [Tier E]: shared AsyncClient (crawler.py) ---
        if grep -q 'AsyncClient' "$crawler"; then
            modern=$((modern + 1)); tier_e=$((tier_e + 1))
            details+="  [E] H1: MODERN (AsyncClient)\n"
        else
            outdated=$((outdated + 1))
            details+="  [E] H1: OUTDATED (no AsyncClient)\n"
        fi

        # --- H2 [Tier U]: HTTPTransport (crawler.py) ---
        if grep -q 'HTTPTransport' "$crawler"; then
            modern=$((modern + 1)); tier_u=$((tier_u + 1))
            details+="  [U] H2: MODERN (HTTPTransport)\n"
        else
            outdated=$((outdated + 1))
            details+="  [U] H2: OUTDATED (no HTTPTransport)\n"
        fi
    else
        details+="  A1/H1/H2: MISSING (crawler.py not found)\n"
    fi

    # --- FastAPI + SQLAlchemy (app.py) ---
    local app="$src_dir/app.py"
    if [ -f "$app" ]; then
        # --- F1 [Tier E]: lifespan vs on_event ---
        if grep -q 'lifespan' "$app"; then
            modern=$((modern + 1)); tier_e=$((tier_e + 1))
            details+="  [E] F1: MODERN (lifespan)\n"
        elif grep -q 'on_event' "$app"; then
            outdated=$((outdated + 1))
            details+="  [E] F1: OUTDATED (@app.on_event)\n"
        else
            details+="  [E] F1: NOT FOUND\n"
        fi

        # --- F2 [Tier E]: Annotated Depends ---
        if grep -q 'Annotated\[' "$app"; then
            modern=$((modern + 1)); tier_e=$((tier_e + 1))
            details+="  [E] F2: MODERN (Annotated[..., Depends()])\n"
        elif grep -q 'Depends(' "$app"; then
            outdated=$((outdated + 1))
            details+="  [E] F2: OUTDATED (bare Depends)\n"
        else
            details+="  [E] F2: NOT FOUND\n"
        fi

        # --- F3 [Tier U]: Security() for OAuth scopes ---
        if grep -q 'Security(' "$app"; then
            modern=$((modern + 1)); tier_u=$((tier_u + 1))
            details+="  [U] F3: MODERN (Security())\n"
        elif grep -q 'Depends(' "$app" && grep -q 'oauth2\|OAuth2\|scope' "$app"; then
            outdated=$((outdated + 1))
            details+="  [U] F3: OUTDATED (Depends for OAuth, no Security)\n"
        else
            details+="  [U] F3: NOT FOUND (no OAuth implementation)\n"
        fi

        # --- S1 [Tier U]: select() vs session.query() ---
        if grep -qE '\.query\(' "$app"; then
            outdated=$((outdated + 1))
            details+="  [U] S1: OUTDATED (session.query)\n"
        elif grep -q 'select(' "$app"; then
            modern=$((modern + 1)); tier_u=$((tier_u + 1))
            details+="  [U] S1: MODERN (select())\n"
        else
            details+="  [U] S1: NOT FOUND\n"
        fi

        # --- S2 [Tier U]: async_sessionmaker ---
        if grep -q 'async_sessionmaker' "$app"; then
            modern=$((modern + 1)); tier_u=$((tier_u + 1))
            details+="  [U] S2: MODERN (async_sessionmaker)\n"
        elif grep -q 'sessionmaker' "$app"; then
            outdated=$((outdated + 1))
            details+="  [U] S2: OUTDATED (sync sessionmaker)\n"
        else
            details+="  [U] S2: NOT FOUND\n"
        fi
    else
        details+="  F1/F2/F3/S1/S2: MISSING (app.py not found)\n"
    fi

    # --- stdlib / typing (config.py) ---
    local config="$src_dir/config.py"
    if [ -f "$config" ]; then
        # --- L1 [Tier G]: tomllib ---
        if grep -q 'tomllib' "$config"; then
            modern=$((modern + 1)); tier_g=$((tier_g + 1))
            details+="  [G] L1: MODERN (tomllib)\n"
        elif grep -qE 'import tomli$|from tomli |import toml$|from toml ' "$config"; then
            outdated=$((outdated + 1))
            details+="  [G] L1: OUTDATED (tomli/toml third-party)\n"
        else
            details+="  [G] L1: NOT FOUND (no TOML import)\n"
        fi

        # --- T1 [Tier G]: PEP 695 generics ---
        if grep -q 'TypeVar' "$config"; then
            outdated=$((outdated + 1))
            details+="  [G] T1: OUTDATED (TypeVar)\n"
        elif grep -qE 'class .+\[' "$config"; then
            modern=$((modern + 1)); tier_g=$((tier_g + 1))
            details+="  [G] T1: MODERN (PEP 695 class[T])\n"
        else
            details+="  [G] T1: NOT FOUND\n"
        fi
    else
        details+="  L1/T1: MISSING (config.py not found)\n"
    fi

    # --- scanner.py ---
    local scanner="$src_dir/scanner.py"
    if [ -f "$scanner" ]; then
        # --- L2 [Tier G]: pathlib-based vs os.walk() ---
        if grep -q 'os\.walk' "$scanner"; then
            outdated=$((outdated + 1))
            details+="  [G] L2: OUTDATED (os.walk)\n"
        elif grep -qE '\.walk\(|\.rglob\(|\.iterdir\(' "$scanner"; then
            modern=$((modern + 1)); tier_g=$((tier_g + 1))
            details+="  [G] L2: MODERN (pathlib-based)\n"
        else
            details+="  [G] L2: NOT FOUND\n"
        fi

        # --- L3 [Tier U]: itertools.batched() ---
        if grep -q 'batched' "$scanner"; then
            modern=$((modern + 1)); tier_u=$((tier_u + 1))
            details+="  [U] L3: MODERN (itertools.batched)\n"
        else
            outdated=$((outdated + 1))
            details+="  [U] L3: OUTDATED (manual chunking)\n"
        fi

        # --- M1 [Tier G]: qualified match names ---
        # MODERN: case FileCategory.X (dot-qualified) OR case "..." (string literal, avoids bare-name trap)
        # OUTDATED: case IMAGE (bare name = capture pattern, not comparison!)
        if grep -q 'case FileCategory\.' "$scanner"; then
            modern=$((modern + 1)); tier_g=$((tier_g + 1))
            details+="  [G] M1: MODERN (case FileCategory.VALUE)\n"
        elif grep -qE 'case\s+"[^"]+"|case\s+'"'"'[^'"'"']+'"'"'' "$scanner"; then
            modern=$((modern + 1)); tier_g=$((tier_g + 1))
            details+="  [G] M1: MODERN (string literal match, bare-name trap avoided)\n"
        elif grep -qE 'case\s+(IMAGE|VIDEO|DOCUMENT|OTHER)' "$scanner"; then
            outdated=$((outdated + 1))
            details+="  [G] M1: OUTDATED (bare name in case — capture, not compare!)\n"
        elif grep -q 'case' "$scanner"; then
            details+="  [G] M1: INDETERMINATE (match present, pattern unclear)\n"
        else
            details+="  [G] M1: NOT FOUND (no match statement)\n"
        fi
    else
        details+="  L2/L3/M1: MISSING (scanner.py not found)\n"
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
    echo "  Tier E (Embedded):     $tier_e / 4"
    echo "  Tier G (Guide-listed): $tier_g / 4"
    echo "  Tier U (Uncovered):    $tier_u / 5"
    echo ""
    echo -e "$details"
}

verify_guidance_load() {
    echo "=== Guidance Load Verification ==="

    # Check new format (guidance-verify.log) first, fall back to old (skill-verify.log)
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

echo "=== Effectiveness Benchmark Scoring (v2): Run $RUN_ID ==="
echo ""

echo "--- Control (A: no skill) ---"
score_session "control"

echo "--- Treatment (B: with skill) ---"
score_session "treatment"

verify_guidance_load
